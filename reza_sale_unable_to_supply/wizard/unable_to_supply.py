# -*- coding: utf-8 -*-
"""Cannot Supply: take a quantity off a confirmed order and credit it.

The whole job runs in one transaction. If any step raises, nothing is written:
no quantity changes, no credit note, no chatter.

Why the credit note is built through `account.move.reversal` rather than by
hand: that wizard is exactly what staff click today (Invoice > Credit Note >
Reverse). It fills the journal, dates, fiscal position, reference and
`reversed_entry_id` the same way, and the reversed lines keep their
`sale_line_ids` (sale/models/account_move_line.py:19-21), so the order line's
invoiced quantity drops with the credit. The only thing done on top is what
staff kept getting wrong: keep the removed lines, at the removed quantity, and
delete the rest.

Posting a draft credit note whose `reversed_entry_id` is posted makes Odoo
match the two receivable lines itself (account/models/account_move.py:5210,
`_reconcile_reversed_moves`). When the invoice is already settled by a payment
that carries a journal entry, there is nothing left to match, and the credit
note stays open for the refund payment to be registered against it.
"""
from collections import defaultdict

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools import float_compare, float_is_zero, format_amount


class RezaUnableSupplyWizard(models.TransientModel):
    _name = "reza.unable.supply.wizard"
    _description = "Cannot Supply"

    order_id = fields.Many2one("sale.order", required=True, readonly=True, ondelete="cascade")
    reason = fields.Char(required=True, default=lambda self: _("Unable to supply"))
    line_ids = fields.One2many("reza.unable.supply.wizard.line", "wizard_id")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env["sale.order"].browse(res.get("order_id") or self.env.context.get("default_order_id"))
        if order and "line_ids" in fields_list:
            res["line_ids"] = [
                Command.create({"sale_line_id": line.id})
                for line in order.order_line
                if self._is_removable(line)
            ]
        return res

    @api.model
    def _is_removable(self, line):
        """Product and delivery lines only. A reward or discount line is never
        offered: its amount is derived from the other lines, and taking it off
        by hand would hand the customer the discount twice."""
        if line.display_type or line.is_downpayment:
            return False
        if "is_reward_line" in line._fields and line.is_reward_line:
            return False
        return True

    # ------------------------------------------------------------------ apply
    def action_apply(self):
        """Button target, so it must stay public. Everything it does is gated
        here, server side: `groups=` on the view only hides the button."""
        self.ensure_one()
        self._check_rights()
        todo, refunds = self._remove_and_credit()
        self._log(self.order_id, todo, refunds)

        if not refunds:
            return {"type": "ir.actions.act_window_close"}
        action = {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "name": _("Credit Notes"),
            "context": {"default_move_type": "out_refund"},
        }
        if len(refunds) == 1:
            action.update(view_mode="form", res_id=refunds.id)
        else:
            action.update(view_mode="list,form", domain=[("id", "in", refunds.ids)])
        return action

    def _check_rights(self):
        user = self.env.user
        if not (user.has_group("sales_team.group_sale_salesman")
                and user.has_group("account.group_account_invoice")):
            raise AccessError(_("Cannot Supply needs both Sales and Invoicing rights."))

    def _remove_and_credit(self):
        """Lower the order, shrink the delivery, credit what was invoiced.
        Shared with the Exchange wizard. Returns (wizard lines acted on, credit notes)."""
        order = self.order_id
        prec = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        todo = self.line_ids.filtered(
            lambda wl: float_compare(wl.qty_to_remove, 0.0, precision_digits=prec) > 0)
        self._check_can_apply(order, todo, prec)

        # Work out the credit BEFORE the quantity changes: it is whatever has
        # been invoiced beyond the quantity that will remain.
        credit = {}
        for wl in todo:
            sol = wl.sale_line_id
            over = sol.qty_invoiced - (sol.product_uom_qty - wl.qty_to_remove)
            if float_compare(over, 0.0, precision_digits=prec) > 0:
                credit[sol] = over
        allocation = self._allocate(credit, prec)

        for wl in todo:
            sol = wl.sale_line_id
            # `skip_procurement`: do NOT let sale_stock push a negative
            # procurement. It only reduces the delivery when the new move can
            # merge into the old one (`_prepare_merge_moves_distinct_fields`:
            # same cost, deadline, procure method ...). When it cannot, Odoo
            # creates a RETURN RECEIPT from the customer instead and leaves the
            # delivery at the old quantity. Seen on a copy of WYN00819: 5 -> 4
            # left WYN/OUT at 5 and raised WYN/IN for 1. So the delivery is
            # reduced here, directly.
            sol.with_context(skip_procurement=True).product_uom_qty = sol.product_uom_qty - wl.qty_to_remove
            self._reduce_delivery(sol, wl.qty_to_remove, prec)

        refunds = self.env["account.move"]
        for invoice, per_line in allocation.items():
            refunds |= self._make_credit_note(invoice, per_line)
        return todo, refunds

    def _check_can_apply(self, order, todo, prec):
        if order.state != "sale":
            raise UserError(_("Only a confirmed sale order can be changed this way."))
        if order.locked:
            raise UserError(_("%s is locked. Ask a sales manager to unlock it first.", order.name))
        if not todo:
            raise UserError(_("Enter the quantity you cannot supply on at least one line."))
        self._check_edbert_purchase(order)
        for wl in todo:
            if wl.sale_line_id.order_id != order:
                raise UserError(_("A line does not belong to %s.", order.name))
            if float_compare(wl.qty_to_remove, wl.max_qty, precision_digits=prec) > 0:
                raise UserError(_(
                    "%(product)s: you can remove at most %(max)s. The rest has already been "
                    "delivered; use a return for that.",
                    product=wl.sale_line_id.product_id.display_name, max=wl.max_qty))
        drafts = todo.sale_line_id.invoice_lines.move_id.filtered(
            lambda m: m.state == "draft" and m.move_type in ("out_invoice", "out_refund"))
        if drafts:
            raise UserError(_(
                "This order has a draft invoice or credit note (%s). Confirm or delete it first.",
                ", ".join(drafts.mapped("display_name"))))

    def _check_edbert_purchase(self, order):
        """Edbert bridge (reza_ecom_intercompany_po, optional here). It raises
        the Edbert purchase only once the order has FULLY shipped, and for
        qty_delivered, so an item removed before dispatch never reaches
        Edbert. A purchase already linked means that assumption no longer
        holds, and changing the order would leave Edbert billing for goods
        the customer never got. A person must handle that one -- unless the
        caller sends the goods back to Edbert itself (reza_exchange_shipped
        overrides this for exactly that case)."""
        if "reza_edbert_purchase_id" in order._fields:
            purchase = order.sudo().reza_edbert_purchase_id
            if purchase and purchase.state != "cancel":
                raise UserError(_(
                    "Edbert purchase %(po)s is already raised for %(so)s. Change it by hand.",
                    po=purchase.name, so=order.name))

    @api.model
    def _open_deliveries(self, sol):
        return sol.move_ids.filtered(
            lambda m: m.state not in ("done", "cancel") and m.location_dest_id.usage == "customer")

    def _reduce_delivery(self, sol, qty, prec):
        """Take `qty` (order-line UoM) off the line's open delivery moves,
        newest first. Every warehouse here delivers in one step, so there is
        no pick or pack move behind the delivery to adjust as well.

        A move the warehouse has already marked picked is not touched: the
        goods may be in a box. That raises, and the whole run rolls back."""
        remaining = sol.product_uom._compute_quantity(qty, sol.product_id.uom_id)
        for move in self._open_deliveries(sol).sorted("id", reverse=True):
            if float_is_zero(remaining, precision_digits=prec):
                break
            if move.picked:
                raise UserError(_(
                    "%(picking)s is already picked for %(product)s. Unpick it first, then try again.",
                    picking=move.picking_id.name, product=sol.product_id.display_name))
            move_qty = move.product_uom._compute_quantity(move.product_uom_qty, sol.product_id.uom_id)
            if float_compare(move_qty, remaining, precision_digits=prec) <= 0:
                move._action_cancel()
                remaining -= move_qty
            else:
                move._do_unreserve()
                move.product_uom_qty = sol.product_id.uom_id._compute_quantity(
                    move_qty - remaining, move.product_uom)
                move._action_assign()
                remaining = 0.0

    def _allocate(self, credit, prec):
        """Spread each line's credit over its posted invoices, newest first,
        never crediting an invoice line for more than it still carries.

        Returns {invoice: {invoice_line: quantity in the invoice line's UoM}}.
        """
        allocation = defaultdict(dict)
        for sol, qty in credit.items():
            posted = sol.invoice_lines.filtered(lambda l: l.move_id.state == "posted")
            invoices = posted.filtered(lambda l: l.move_id.move_type == "out_invoice").move_id
            remaining = qty
            for invoice in invoices.sorted(lambda m: (m.invoice_date or m.date, m.id), reverse=True):
                inv_lines = posted.filtered(lambda l: l.move_id == invoice)
                if len(inv_lines) != 1:
                    raise UserError(_(
                        "%(inv)s carries %(product)s on more than one line. Credit it by hand.",
                        inv=invoice.name, product=sol.product_id.display_name))
                inv_line = inv_lines
                already = sum(
                    r.product_uom_id._compute_quantity(r.quantity, sol.product_uom)
                    for r in posted
                    if r.move_id.move_type == "out_refund" and r.move_id.reversed_entry_id == invoice
                )
                available = inv_line.product_uom_id._compute_quantity(inv_line.quantity, sol.product_uom) - already
                take = min(available, remaining)
                if float_compare(take, 0.0, precision_digits=prec) <= 0:
                    continue
                allocation[invoice][inv_line] = sol.product_uom._compute_quantity(take, inv_line.product_uom_id)
                remaining -= take
                if float_is_zero(remaining, precision_digits=prec):
                    break
            if float_compare(remaining, 0.0, precision_digits=prec) > 0:
                raise UserError(_(
                    "Could not find a posted invoice to credit %(qty)s of %(product)s against. "
                    "Credit it by hand.", qty=remaining, product=sol.product_id.display_name))
        return allocation

    def _make_credit_note(self, invoice, per_line):
        reversal = self.env["account.move.reversal"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({"reason": self.reason, "journal_id": invoice.journal_id.id})
        reversal.reverse_moves()
        refund = reversal.new_move_ids
        refund.ensure_one()

        # Match each reversed line to its source by order line. `_allocate`
        # already refused an invoice with two lines for one order line, so the
        # match is unambiguous.
        wanted = {inv_line.sale_line_ids: qty for inv_line, qty in per_line.items()}
        commands = []
        for line in refund.invoice_line_ids:
            qty = wanted.get(line.sale_line_ids) if line.sale_line_ids else None
            if line.display_type == "product" and qty is not None:
                commands.append(Command.update(line.id, {"quantity": qty}))
            else:
                commands.append(Command.delete(line.id))
        refund.write({"invoice_line_ids": commands})

        kept = refund.invoice_line_ids.filtered(lambda l: l.display_type == "product")
        if len(kept) != len(per_line):
            raise UserError(_("The credit note for %s did not come out as expected. Nothing was changed.",
                              invoice.name))

        # A negative line on the invoice is a discount or a reward. The full
        # line price would then refund more than the customer paid, so leave
        # the credit note in draft for a person to check.
        if not self._has_discount(invoice):
            refund.action_post()
        return refund

    @api.model
    def _has_discount(self, invoice):
        return any(
            float_compare(line.price_subtotal, 0.0, precision_rounding=invoice.currency_id.rounding) < 0
            for line in invoice.invoice_line_ids
            if line.display_type == "product"
        )

    def _log(self, order, todo, refunds):
        items = Markup("").join(
            Markup("<li>%s × %s</li>") % (wl.qty_to_remove, wl.sale_line_id.product_id.display_name)
            for wl in todo
        )
        body = Markup("<p><b>%s</b> (%s)</p><ul>%s</ul>") % (_("Cannot supply"), self.reason, items)

        if not refunds:
            body += Markup("<p>%s</p>") % _("Nothing was invoiced for these items, so no credit note "
                                            "and no refund are needed.")
        for refund in refunds:
            amount = format_amount(self.env, refund.amount_total, refund.currency_id)
            if refund.state == "draft":
                body += Markup("<p>%s</p>") % _(
                    "Credit note %(ref)s for %(amount)s is in DRAFT: the invoice carries a discount, "
                    "so check the amount, then click Confirm.",
                    ref=refund._get_html_link(), amount=amount)
            elif refund.currency_id.is_zero(refund.amount_residual):
                body += Markup("<p>%s</p>") % _(
                    "Credit note %(ref)s for %(amount)s is posted and matched to %(inv)s.",
                    ref=refund._get_html_link(), amount=amount,
                    inv=refund.reversed_entry_id._get_html_link())
            else:
                body += Markup("<p>%s</p>") % _(
                    "Credit note %(ref)s for %(amount)s is posted. The invoice was already paid, so "
                    "after the refund, click Register Payment on the credit note.",
                    ref=refund._get_html_link(), amount=amount)

        if refunds:
            total = format_amount(self.env, sum(refunds.mapped("amount_total")), order.currency_id)
            done = order.transaction_ids.filtered(lambda t: t.state == "done" and t.operation != "refund")
            paid_by = ", ".join(
                "%s (%s)" % (t.provider_id.name, t.provider_reference or t.reference) for t in done
            ) or _("the original payment method")
            body += Markup("<p><b>%s</b></p>") % _(
                "Refund %(total)s to the customer in %(paid_by)s. Odoo does not send this refund.",
                total=total, paid_by=paid_by)

        order.message_post(body=body)
        for refund in refunds:
            refund.message_post(body=Markup("<p>%s</p>") % _(
                "Created by Cannot Supply on %s.", order._get_html_link()))


class RezaUnableSupplyWizardLine(models.TransientModel):
    _name = "reza.unable.supply.wizard.line"
    _description = "Cannot Supply line"

    wizard_id = fields.Many2one("reza.unable.supply.wizard", required=True, ondelete="cascade")
    sale_line_id = fields.Many2one("sale.order.line", required=True, readonly=True)
    product_id = fields.Many2one(related="sale_line_id.product_id")
    product_uom = fields.Many2one(related="sale_line_id.product_uom")
    ordered_qty = fields.Float(related="sale_line_id.product_uom_qty", digits="Product Unit of Measure")
    delivered_qty = fields.Float(related="sale_line_id.qty_delivered", digits="Product Unit of Measure")
    invoiced_qty = fields.Float(related="sale_line_id.qty_invoiced", digits="Product Unit of Measure")
    price_unit = fields.Float(related="sale_line_id.price_unit")
    max_qty = fields.Float(compute="_compute_max_qty", digits="Product Unit of Measure")
    qty_to_remove = fields.Float("Cannot supply", digits="Product Unit of Measure", default=0.0)

    @api.depends("sale_line_id.product_uom_qty", "sale_line_id.qty_delivered")
    def _compute_max_qty(self):
        for line in self:
            sol = line.sale_line_id
            line.max_qty = max(sol.product_uom_qty - sol.qty_delivered, 0.0)
