# -*- coding: utf-8 -*-
"""Exchange (shipped): the customer sent an item back and wants another one.

Use it once the item is back in the shed. In one transaction:

1. Receive the item back: a return of the delivery, validated. That lowers the
   line's delivered quantity.
2. Credit it: the Cannot Supply step lowers the ordered quantity to match and
   raises the credit note for exactly that quantity.
3. Put the replacement on a NEW sale order, linked to this one. Not on this
   order: the Edbert bridge buys from Edbert once per order, after it ships, so
   a line added here after the purchase was raised would never be bought. A new
   order goes through the bridge like any other.
4. Invoice the replacement and match the credit note against that invoice, not
   against the original. Same price -> both read Paid; dearer -> the new
   invoice shows what the customer owes; cheaper -> the credit note shows what
   to refund. (Same reasoning as the Exchange wizard, wizard/exchange.py in
   reza_sale_unable_to_supply.)
5. Queue the returned item to go back to Edbert (reza.edbert.return). That part
   reaches another database, so it runs from a cron AFTER this transaction
   commits, never inside it.

Price rule (Rez, 2026-10-08, same as Exchange): if the replacement differs from
what the customer paid by less than $1.00, the customer keeps the price paid.
"""
from collections import defaultdict

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools import float_compare, float_is_zero, format_amount

from ..models.stock_compat import confirm_return, draft_return, validate_return

KEEP_PRICE_BELOW = 1.00  # dollars, on the line total


class RezExchangeShippedWizard(models.TransientModel):
    _name = "reza.exchange.shipped.wizard"
    _description = "Exchange (shipped)"

    order_id = fields.Many2one("sale.order", required=True, readonly=True, ondelete="cascade")
    line_ids = fields.One2many("reza.exchange.shipped.wizard.line", "wizard_id")
    charge_shipping = fields.Boolean(
        default=True,
        help="Put the shipping the customer paid on the first order onto the replacement "
        "order too. Untick it when the customer should not pay shipping again, for "
        "example when the item was faulty.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env["sale.order"].browse(
            res.get("order_id") or self.env.context.get("default_order_id"))
        if order and "line_ids" in fields_list:
            prec = self.env["decimal.precision"].precision_get("Product Unit")
            res["line_ids"] = [
                Command.create({"sale_line_id": line.id})
                for line in order.order_line
                if not line.display_type and not line.is_downpayment
                and line.product_id.type == "consu"
                and not ("is_reward_line" in line._fields and line.is_reward_line)
                and float_compare(line.qty_delivered, 0.0, precision_digits=prec) > 0
            ]
        return res

    # ------------------------------------------------------------------ apply
    def action_apply(self):
        """Button target, so it must stay public. Rights are checked here,
        server side: `groups=` on the view only hides the button."""
        self.ensure_one()
        self._check_rights()
        order = self.order_id
        prec = self.env["decimal.precision"].precision_get("Product Unit")
        todo = self.line_ids.filtered(
            lambda wl: float_compare(wl.qty_to_exchange, 0.0, precision_digits=prec) > 0)
        self._check_can_apply(order, todo, prec)
        edbert = self._edbert_purchase(order)

        # What the customer paid for the old items, read before anything changes.
        paid = {wl: wl.sale_line_id.price_reduce_taxinc * wl.qty_to_exchange for wl in todo}

        pairs = [(wl.sale_line_id, wl.qty_to_exchange) for wl in todo]
        self._return_from_customer(pairs, prec)

        remover = self.env["reza.unable.supply.wizard"].create({
            "order_id": order.id,
            "reason": _("Exchange (returned)"),
            "line_ids": [Command.create({"sale_line_id": wl.sale_line_id.id,
                                         "qty_to_remove": wl.qty_to_exchange}) for wl in todo],
        })
        # The returned items go back to Edbert through _queue_edbert, so the
        # "Edbert purchase already raised" refusal does not apply here.
        __, refunds = remover._remove_and_credit(edbert_handled=True)

        new_order, kept = self._make_replacement(order, todo, paid)

        invoice = self.env["account.move"]
        if refunds:
            invoice = new_order._create_invoices()
            invoice.action_post()
            self.env["reza.exchange.wizard"]._rematch(refunds, invoice)

        rows = self._queue_edbert(order, pairs, edbert)
        self._log(order, new_order, todo, kept, paid, refunds, invoice, rows)
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": new_order.id,
            "view_mode": "form",
            "target": "current",
        }

    # ----------------------------------------------------------------- checks
    def _check_rights(self):
        user = self.env.user
        if not (user.has_group("sales_team.group_sale_salesman")
                and user.has_group("account.group_account_invoice")
                and user.has_group("stock.group_stock_user")):
            raise AccessError(_("Exchange (shipped) needs Sales, Invoicing and Inventory rights."))

    def _check_can_apply(self, order, todo, prec):
        if order.state != "sale":
            raise UserError(_("Only a confirmed sale order can be exchanged."))
        if order.locked:
            raise UserError(_("%s is locked. Ask a sales manager to unlock it first.", order.name))
        if not todo:
            raise UserError(_("Enter the quantity to exchange on at least one line."))
        for wl in todo:
            sol = wl.sale_line_id
            if sol.order_id != order:
                raise UserError(_("A line does not belong to %s.", order.name))
            if float_compare(wl.qty_to_exchange, sol.qty_delivered, precision_digits=prec) > 0:
                raise UserError(_(
                    "%(product)s: only %(qty)s was delivered, so only %(qty)s can come back.",
                    product=sol.product_id.display_name, qty=sol.qty_delivered))
            if not wl.new_product_id:
                raise UserError(_("Choose the replacement for %s. It can be the same product.",
                                  sol.product_id.display_name))
            if wl.new_product_id.invoice_policy != "order":
                raise UserError(_("%s is invoiced on delivery, so it cannot be exchanged here.",
                                  wl.new_product_id.display_name))
        # An invoice that carries a discount line makes the credit note a
        # draft for a person to check, and a draft cannot be matched.
        invoices = order.invoice_ids.filtered(
            lambda m: m.state == "posted" and m.move_type == "out_invoice")
        if any(self.env["reza.unable.supply.wizard"]._has_discount(inv) for inv in invoices):
            raise UserError(_("%s was invoiced with a discount. Do this exchange by hand.",
                              order.name))

    @api.model
    def _edbert_purchase(self, order):
        """The Edbert purchase the returned items go back against, or empty.

        Empty when Edbert never supplied this order: its company has no bridge
        settings, or nothing on it is an Edbert product. Refuses while the
        bridge is still working on the order -- the returned item would go
        back against a purchase that does not exist yet, or a bill that is not
        posted."""
        if "reza_edbert_purchase_id" not in order._fields:
            return self.env["purchase.order"]
        purchase = order.sudo().reza_edbert_purchase_id
        status = order.reza_edbert_status
        if not purchase:
            if status in ("pending", "failed") and order._reza_api_company():
                raise UserError(_(
                    "The Edbert purchase for %s is not raised yet. Try again once it is.",
                    order.name))
            return self.env["purchase.order"]
        if purchase.state not in ("purchase", "done") or not order.reza_edbert_transfer_done \
                or not order.reza_edbert_invoiced:
            raise UserError(_(
                "The Edbert paperwork for %(so)s (%(po)s) is not finished yet: the transfer "
                "or the bill is still open. Try again once it completes.",
                so=order.name, po=purchase.name))
        return purchase

    # ------------------------------------------------------------------ stock
    @api.model
    def _return_from_customer(self, pairs, prec):
        """Receive the items back: one return per delivery, newest delivery
        first, validated at once (the item is already in the shed).

        `pairs` is [(sale.order.line, quantity in the line's UoM)]. Shared with
        the Refund (shipped) wizard."""
        per_picking = defaultdict(dict)
        for sol, qty in pairs:
            moves = sol.move_ids.filtered(
                lambda m: m.state == "done" and m.location_dest_id.usage == "customer"
                and not m.origin_returned_move_id)
            remaining = sol.product_uom_id._compute_quantity(qty, sol.product_id.uom_id)
            for move in moves.sorted("id", reverse=True):
                if float_is_zero(remaining, precision_digits=prec):
                    break
                returned = sum(move.returned_move_ids.filtered(
                    lambda r: r.state == "done").mapped("product_qty"))
                free = move.product_qty - returned
                take = min(free, remaining)
                if float_compare(take, 0.0, precision_digits=prec) <= 0:
                    continue
                per_picking[move.picking_id][move] = take
                remaining -= take
            if float_compare(remaining, 0.0, precision_digits=prec) > 0:
                raise UserError(_("Could not find a delivery of %s to return it against.",
                                  sol.product_id.display_name))

        for picking, qtys in per_picking.items():
            # Odoo 20: no return wizard. `qtys` is in the product's own unit
            # (move.product_qty); a return move carries the original's unit.
            ret = draft_return(picking)
            for move in ret.move_ids:
                orig = move.origin_returned_move_id
                move.product_uom_qty = move.product_id.uom_id._compute_quantity(
                    qtys[orig], move.uom_id) if orig in qtys else 0.0
            ret = confirm_return(ret)
            validate_return(ret, _("The customer return"))

    # -------------------------------------------------------------- new order
    def _make_replacement(self, order, todo, paid):
        vals = {
            "partner_id": order.partner_id.id,
            "partner_invoice_id": order.partner_invoice_id.id,
            "partner_shipping_id": order.partner_shipping_id.id,
            "company_id": order.company_id.id,
            "pricelist_id": order.pricelist_id.id,
            "warehouse_id": order.warehouse_id.id,
            "team_id": order.team_id.id,
            "user_id": order.user_id.id,
            "fiscal_position_id": order.fiscal_position_id.id,
            "payment_term_id": order.payment_term_id.id,
            "origin": order.name,
            "client_order_ref": order.client_order_ref or order.name,
            "reza_exchange_origin_id": order.id,
            "order_line": [Command.create({
                "product_id": wl.new_product_id.id,
                "product_uom_qty": wl.qty_to_exchange,
            }) for wl in todo],
        }
        if "website_id" in order._fields and order.website_id:
            vals["website_id"] = order.website_id.id
        if "carrier_id" in order._fields and order.carrier_id:
            vals["carrier_id"] = order.carrier_id.id
        new_order = self.env["sale.order"].with_company(order.company_id).create(vals)

        kept = {}
        for wl, line in zip(todo, new_order.order_line):
            old = wl.sale_line_id
            kept[wl] = abs(line.price_total - paid[wl]) < KEEP_PRICE_BELOW
            if kept[wl]:
                line.write({"price_unit": old.price_unit, "discount": old.discount,
                            "tax_ids": [Command.set(old.tax_ids.ids)]})
        if self.charge_shipping:
            self._add_shipping(order, new_order)
        # No send_email in the context: the customer is told by staff, not by
        # a second order confirmation they did not place.
        new_order.action_confirm()
        return new_order, kept

    def _add_shipping(self, order, new_order):
        """The same shipping charge the customer paid on the first order.

        Copied from the old delivery line rather than re-quoted from the
        carrier: a re-quote calls Starshipit, may come back different, and
        staff cannot see why. The price and tax are written back after
        `set_delivery_line`, because `_prepare_delivery_line_vals` adjusts
        the amount for fiscal position and tax-included pricing."""
        old = order.order_line.filtered(lambda l: l.is_delivery and not l.display_type)[:1]
        if not old or not order.carrier_id:
            return
        new_order.set_delivery_line(order.carrier_id, old.price_unit)
        line = new_order.order_line.filtered("is_delivery")
        line.write({"price_unit": old.price_unit, "discount": old.discount,
                    "tax_ids": [Command.set(old.tax_ids.ids)]})

    # ----------------------------------------------------------------- Edbert
    @api.model
    def _queue_edbert(self, order, pairs, purchase):
        """`pairs` is [(sale.order.line, quantity)]. Shared with Refund (shipped)."""
        Return = self.env["reza.edbert.return"].sudo()
        if not purchase:
            return Return
        bought = purchase.order_line.product_id
        qty = defaultdict(float)
        for sol, q in pairs:
            if sol.product_id in bought:
                qty[sol.product_id] += q
        rows = Return.create([{
            "sale_order_id": order.id,
            "purchase_id": purchase.id,
            "product_id": product.id,
            "qty": q,
        } for product, q in qty.items()])
        if rows:
            self.env.ref("reza_exchange_shipped.ir_cron_reza_edbert_return").sudo()._trigger()
        return rows

    # -------------------------------------------------------------------- log
    def _log(self, order, new_order, todo, kept, paid, refunds, invoice, rows):
        items = Markup("").join(
            Markup("<li>%s × %s → %s%s</li>") % (
                wl.qty_to_exchange, wl.product_id.display_name, wl.new_product_id.display_name,
                _(" (price kept)") if kept[wl] else "")
            for wl in todo)
        body = Markup("<p><b>%s</b></p><ul>%s</ul>") % (_("Exchange (shipped)"), items)
        body += Markup("<p>%s</p>") % _(
            "Item received back. Replacement order: %s.", new_order._get_html_link())
        currency = order.currency_id
        if refunds:
            owed = invoice.amount_residual
            back = sum(refunds.mapped("amount_residual"))
            links = Markup(", ").join(m._get_html_link() for m in refunds | invoice)
            body += Markup("<p>%s</p>") % _("Documents: %s.", links)
            if not currency.is_zero(owed):
                body += Markup("<p><b>%s</b></p>") % _(
                    "The customer owes %s for the dearer item. Send them a payment link.",
                    format_amount(self.env, owed, currency))
            elif not currency.is_zero(back):
                body += Markup("<p><b>%s</b></p>") % _(
                    "Refund %s to the customer in PayPal or Stripe. Odoo does not send this refund.",
                    format_amount(self.env, back, currency))
            else:
                body += Markup("<p>%s</p>") % _("Same price: nothing to pay and nothing to refund.")
        else:
            change = sum(new_order.mapped("amount_total")) - sum(paid.values())
            body += Markup("<p><b>%s</b></p>") % _(
                "Nothing was invoiced on this order, so no credit note was raised. "
                "The replacement order totals %(total)s (a difference of %(diff)s).",
                total=format_amount(self.env, new_order.amount_total, currency),
                diff=format_amount(self.env, change, currency))
        if rows:
            body += Markup("<p>%s</p>") % _(
                "Going back to Edbert: %s. The return and both credit notes are done in the "
                "background; this order says when they are finished.",
                ", ".join(rows.mapped("name")))
        order.message_post(body=body)
        new_order.message_post(body=Markup("<p>%s</p>") % _(
            "Replacement for items returned on %s.", order._get_html_link()))


class RezExchangeShippedWizardLine(models.TransientModel):
    _name = "reza.exchange.shipped.wizard.line"
    _description = "Exchange (shipped) line"

    wizard_id = fields.Many2one("reza.exchange.shipped.wizard", required=True, ondelete="cascade")
    sale_line_id = fields.Many2one("sale.order.line", required=True, readonly=True)
    product_id = fields.Many2one(related="sale_line_id.product_id")
    product_tmpl_id = fields.Many2one(related="sale_line_id.product_id.product_tmpl_id")
    delivered_qty = fields.Float(related="sale_line_id.qty_delivered",
                                 digits="Product Unit")
    price_unit = fields.Float(related="sale_line_id.price_unit")
    qty_to_exchange = fields.Float("Returned", digits="Product Unit", default=0.0)
    new_product_id = fields.Many2one(
        "product.product", string="Replacement",
        domain="[('sale_ok', '=', True), ('type', '=', 'consu')]")
