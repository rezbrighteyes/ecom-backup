# Copyright 2020 Tecnativa - Ernesto Tejeda
# Copyright 2023 Michael Tietz (MT Software) <mtietz@mt-software.de>
# Copyright 2025 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
#
# Odoo 20 port: core deleted the `stock.return.picking` wizard (a return is
# now `stock.picking._create_return()`, a draft picking). This module used to
# extend that wizard with "Create RMAs". It now owns an equivalent wizard,
# `rma.return.picking`, with the same fields and methods, opened from the
# "Return / RMA" button on a done delivery.
from copy import deepcopy

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ReturnPickingLine(models.TransientModel):
    _name = "rma.return.picking.line"
    _rec_name = "product_id"
    _description = "RMA Return Picking Line"

    product_id = fields.Many2one("product.product", string="Product", required=True)
    move_quantity = fields.Float(related="move_id.quantity", string="Move Quantity")
    quantity = fields.Float("Quantity", digits="Product Unit", default=1, required=True)
    uom_id = fields.Many2one(
        "uom.uom", string="Unit of Measure", related="product_id.uom_id"
    )
    wizard_id = fields.Many2one("rma.return.picking", string="Wizard")
    move_id = fields.Many2one("stock.move", "Move")
    to_refund = fields.Boolean(
        string="Update quantities on SO/PO",
        default=True,
        help="Trigger a decrease of the delivered/received quantity in the "
        "associated Sale Order/Purchase Order",
    )

    rma_operation_id = fields.Many2one(
        comodel_name="rma.operation",
        string="Operation",
        compute="_compute_rma_operation_id",
        store=True,
        readonly=False,
    )
    return_product_id = fields.Many2one(
        "product.product",
        help="Product to be returned if it's different from the originally delivered "
        "item.",
    )
    different_return_product = fields.Boolean(
        related="rma_operation_id.different_return_product"
    )

    @api.depends("wizard_id.rma_operation_id")
    def _compute_rma_operation_id(self):
        for rec in self:
            if rec.wizard_id.rma_operation_id:
                rec.rma_operation_id = rec.wizard_id.rma_operation_id

    def _prepare_rma_vals(self):
        self.ensure_one()
        warehouse = self.move_id.picking_id.picking_type_id.warehouse_id
        if not warehouse:
            # Dropship compatibility
            warehouse = self.env["stock.warehouse"].search(
                [("company_id", "=", self.move_id.picking_id.company_id.id)],
                limit=1,
            )
        vals = {
            "move_id": self.move_id.id,
            "product_id": self.move_id.product_id.id,
            "product_uom_qty": self.quantity,
            "product_uom": self.product_id.uom_id.id,
            "location_id": warehouse.rma_loc_id.id,
            "operation_id": self.rma_operation_id.id,
            "return_product_id": self.return_product_id.id,
        }
        # RMA from RMA compatibility
        rma = self.move_id.rma_id
        if rma:
            vals.update(
                partner_id=rma.partner_id.id,
                partner_shipping_id=rma.partner_shipping_id.id,
                partner_invoice_id=rma.partner_invoice_id.id,
            )
        return vals


class ReturnPicking(models.TransientModel):
    _name = "rma.return.picking"
    _description = "RMA Return Picking"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get("active_id") and ctx.get("active_model") == "stock.picking":
            if len(ctx.get("active_ids", [])) > 1:
                raise UserError(self.env._("You may only return one picking at a time."))
            picking = self.env["stock.picking"].browse(ctx.get("active_id"))
            if picking.exists():
                res.update({"picking_id": picking.id})
        return res

    picking_id = fields.Many2one("stock.picking")
    product_return_moves = fields.One2many(
        "rma.return.picking.line",
        "wizard_id",
        "Moves",
        compute="_compute_moves_locations",
        precompute=True,
        readonly=False,
        store=True,
    )
    company_id = fields.Many2one(related="picking_id.company_id")
    create_rma = fields.Boolean(string="Create RMAs")
    picking_type_code = fields.Selection(related="picking_id.picking_type_id.code")
    rma_operation_id = fields.Many2one(
        comodel_name="rma.operation",
        string="Requested operation",
    )

    @api.onchange("create_rma")
    def _onchange_create_rma(self):
        if self.create_rma:
            # We want to avoid setting the return move `to_refund` as it will change
            # the delivered quantities in the sale and set them to invoice.
            self.product_return_moves.to_refund = False

    def _prepare_rma_partner_values(self):
        self.ensure_one()
        partner = self.picking_id.partner_id
        partner_address = partner.address_get(["invoice", "delivery"])
        partner_invoice_id = partner_address.get("invoice", False)
        partner_shipping_id = partner_address.get("delivery", False)
        return (
            partner,
            partner_invoice_id and partner.browse(partner_invoice_id) or partner,
            partner_shipping_id and partner.browse(partner_shipping_id) or partner,
        )

    def _prepare_rma_vals(self):
        partner, partner_invoice, partner_shipping = self._prepare_rma_partner_values()
        origin = self.picking_id.name
        return {
            "user_id": self.env.user.id,
            "partner_id": partner.id,
            "partner_shipping_id": partner_shipping.id,
            "partner_invoice_id": partner_invoice.id,
            "origin": origin,
            "picking_id": self.picking_id.id,
            "company_id": self.company_id.id,
        }

    def _prepare_rma_vals_list(self):
        vals_list = []
        for return_picking in self:
            global_vals = return_picking._prepare_rma_vals()
            for line in return_picking.product_return_moves:
                if not line.move_id or line.uom_id.is_zero(line.quantity):
                    continue
                vals = deepcopy(global_vals)
                vals.update(line._prepare_rma_vals())
                vals_list.append(vals)
        return vals_list

    @api.depends("picking_id")
    def _compute_moves_locations(self):
        for wizard in self:
            if not wizard.picking_id:
                continue
            if wizard.picking_id.state != "done":
                raise UserError(self.env._("You may only return Done pickings."))
            line_fields = list(self.env["rma.return.picking.line"]._fields)
            line_defaults = self.env["rma.return.picking.line"].default_get(line_fields)
            commands = [Command.clear()]
            for move in wizard.picking_id.move_ids:
                if move.state == "cancel" or move.is_scrap:
                    continue
                vals = dict(line_defaults)
                vals.update(wizard._prepare_stock_return_picking_line_vals_from_move(move))
                commands.append(Command.create(vals))
            if len(commands) == 1:
                raise UserError(
                    self.env._(
                        "No products to return (only lines in Done state and not "
                        "fully returned yet can be returned)."
                    )
                )
            wizard.product_return_moves = commands

    @api.model
    def _prepare_stock_return_picking_line_vals_from_move(self, stock_move):
        return {
            "product_id": stock_move.product_id.id,
            "quantity": 0,
            "move_id": stock_move.id,
            "to_refund": stock_move.to_refund,
        }

    def _create_return(self):
        """Plain (non-RMA) return through the Odoo 20 core flow: core drafts
        a return with every move at zero, the wizard's quantities are copied
        onto it, zero moves are dropped, then it is confirmed and reserved."""
        self.ensure_one()
        new_picking = self.picking_id._create_return()
        lines_by_move = {line.move_id: line for line in self.product_return_moves}
        for move in new_picking.move_ids:
            line = lines_by_move.get(move.origin_returned_move_id)
            if not line or line.uom_id.is_zero(line.quantity):
                move.product_uom_qty = 0
                continue
            move.write(
                {
                    "product_uom_qty": line.uom_id._compute_quantity(
                        line.quantity, move.uom_id
                    ),
                    "to_refund": line.to_refund,
                }
            )
        zero = new_picking.move_ids.filtered(
            lambda m: m.uom_id.is_zero(m.product_uom_qty)
        )
        if zero == new_picking.move_ids:
            new_picking.unlink()
            raise UserError(self.env._("Please specify at least one non-zero quantity."))
        zero.unlink()
        new_picking.action_confirm()
        new_picking.action_assign()
        return new_picking

    def action_create_returns_all(self):
        """Set every line to what can still be returned (the done quantity
        less anything already returned), then create the returns."""
        self.ensure_one()
        for line in self.product_return_moves:
            stock_move = line.move_id
            if not stock_move or stock_move.state == "cancel" or stock_move.is_scrap:
                continue
            quantity = stock_move.quantity
            for move in stock_move.move_dest_ids:
                if (
                    not move.origin_returned_move_id
                    or move.origin_returned_move_id != stock_move
                ):
                    continue
                quantity -= move.quantity
            line.quantity = stock_move.product_id.uom_id.round(quantity)
        return self.action_create_returns()

    def action_create_returns(self):
        """Override create_returns method for creating one or more
        'confirmed' RMAs after return a delivery picking in case
        'Create RMAs' checkbox is checked in this wizard.
        New RMAs will be linked to the delivery picking as the origin
        delivery and also RMAs will be linked to the returned picking
        as the 'Receipt'.
        """
        if self.create_rma:
            if not self.picking_id.partner_id:
                raise ValidationError(
                    self.env._(
                        "You must specify the 'Customer' in the "
                        "'Stock Picking' from which RMAs will be created"
                    )
                )
            vals_list = self._prepare_rma_vals_list()
            rmas = self.env["rma"].create(vals_list)
            rmas.action_confirm()
            picking = rmas.reception_move_id.picking_id
            picking = picking and picking[0] or picking
            ctx = dict(self.env.context)
            ctx.update(
                {
                    "default_partner_id": picking.partner_id.id,
                    "search_default_picking_type_id": picking.picking_type_id.id,
                    "search_default_draft": False,
                    "search_default_assigned": False,
                    "search_default_confirmed": False,
                    "search_default_ready": False,
                    "search_default_planning_issues": False,
                    "search_default_available": False,
                }
            )
            return {
                "name": self.env._("Returned Picking"),
                "view_mode": "form,list,calendar",
                "res_model": "stock.picking",
                "res_id": picking.id,
                "type": "ir.actions.act_window",
                "context": ctx,
            }
        new_picking = self._create_return()
        return {
            "name": self.env._("Returned Picking"),
            "view_mode": "form",
            "res_model": "stock.picking",
            "res_id": new_picking.id,
            "type": "ir.actions.act_window",
            "context": self.env.context,
        }
