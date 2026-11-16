# -*- coding: utf-8 -*-
"""Refund (shipped): the customer sent items back and wants their money.

Use it once the items are back in the shed. In one transaction:

1. Receive the items back (a return of the delivery, validated).
2. Credit them through the Cannot Supply step: the ordered quantity drops to
   match, so the order no longer reads "To invoice" and nobody re-bills the
   customer by clicking Create Invoice. Shipping is credited too only when
   "Refund shipping" is ticked.
3. Start a reza.customer.refund row per credit note: an Accounts task with the
   exact amount, provider and transaction -- or, with the setting on and a
   Stripe payment, the refund sent from Odoo. A daily cron then checks the
   provider until the money has really gone back.
4. Queue the items to go back to Edbert (reza.edbert.return), exactly as
   Exchange (shipped) does.

The credit is the price the customer PAID, GST included: it comes from the
invoice line itself (account.move.reversal), never from a figure typed by a
person. MJ00225 was refunded the tax-excluded column, $21.82 short.
"""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools import float_compare, format_amount


class RezRefundShippedWizard(models.TransientModel):
    _name = "reza.refund.shipped.wizard"
    _description = "Refund (shipped)"

    order_id = fields.Many2one("sale.order", required=True, readonly=True, ondelete="cascade")
    line_ids = fields.One2many("reza.refund.shipped.wizard.line", "wizard_id")
    reason = fields.Char(required=True, default=lambda self: _("Customer return"))
    refund_shipping = fields.Boolean(
        default=False,
        help="Also refund the shipping the customer paid. Tick it when the item was faulty, "
        "damaged or the wrong item. Leave it for a change of mind.")
    auto_refund = fields.Boolean(compute="_compute_auto_refund")

    def _compute_auto_refund(self):
        enabled = self.env["reza.customer.refund"]._auto_refund_enabled()
        for wizard in self:
            wizard.auto_refund = enabled

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env["sale.order"].browse(
            res.get("order_id") or self.env.context.get("default_order_id"))
        if order and "line_ids" in fields_list:
            prec = self.env["decimal.precision"].precision_get("Product Unit of Measure")
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
        """Button target, so public. Rights are checked here, server side."""
        self.ensure_one()
        self._check_rights()
        order = self.order_id
        prec = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        todo = self.line_ids.filtered(
            lambda wl: float_compare(wl.qty_to_return, 0.0, precision_digits=prec) > 0)
        self._check_can_apply(order, todo, prec)
        exchange = self.env["reza.exchange.shipped.wizard"]
        edbert = exchange._edbert_purchase(order)
        pairs = [(wl.sale_line_id, wl.qty_to_return) for wl in todo]

        exchange._return_from_customer(pairs, prec)

        remove = [Command.create({"sale_line_id": sol.id, "qty_to_remove": qty})
                  for sol, qty in pairs]
        shipping = self._shipping_line(order) if self.refund_shipping else self.env["sale.order.line"]
        if shipping:
            remove.append(Command.create({"sale_line_id": shipping.id,
                                          "qty_to_remove": shipping.product_uom_qty}))
        remover = self.env["reza.unable.supply.wizard"].create({
            "order_id": order.id, "reason": self.reason, "line_ids": remove})
        # The goods go back to Edbert through _queue_edbert below, so the
        # "Edbert purchase already raised" refusal does not apply.
        __, refunds = remover._remove_and_credit(edbert_handled=True)

        tracked = self.env["reza.customer.refund"]._start(order, refunds)
        rows = exchange._queue_edbert(order, pairs, edbert)
        self._log(order, todo, shipping, refunds, tracked, rows)
        for refund in refunds:
            refund.message_post(body=Markup("<p>%s</p>") % _(
                "Created by Refund (shipped) on %s.", order._get_html_link()))
        if len(refunds) == 1:
            return {"type": "ir.actions.act_window", "res_model": "account.move",
                    "res_id": refunds.id, "view_mode": "form", "target": "current"}
        return {"type": "ir.actions.act_window", "res_model": "sale.order",
                "res_id": order.id, "view_mode": "form", "target": "current"}

    # ----------------------------------------------------------------- checks
    def _check_rights(self):
        user = self.env.user
        if not (user.has_group("sales_team.group_sale_salesman")
                and user.has_group("account.group_account_invoice")
                and user.has_group("stock.group_stock_user")):
            raise AccessError(_("Refund (shipped) needs Sales, Invoicing and Inventory rights."))

    def _check_can_apply(self, order, todo, prec):
        if order.state != "sale":
            raise UserError(_("Only a confirmed sale order can be refunded this way."))
        if order.locked:
            raise UserError(_("%s is locked. Ask a sales manager to unlock it first.", order.name))
        if not todo:
            raise UserError(_("Enter the quantity that came back on at least one line."))
        for wl in todo:
            sol = wl.sale_line_id
            if sol.order_id != order:
                raise UserError(_("A line does not belong to %s.", order.name))
            if float_compare(wl.qty_to_return, sol.qty_delivered, precision_digits=prec) > 0:
                raise UserError(_(
                    "%(product)s: only %(qty)s was delivered, so only %(qty)s can come back.",
                    product=sol.product_id.display_name, qty=sol.qty_delivered))
        if self.refund_shipping and not self._shipping_line(order):
            raise UserError(_("%s has no invoiced shipping to refund. Untick Refund shipping.",
                              order.name))
        invoices = order.invoice_ids.filtered(
            lambda m: m.state == "posted" and m.move_type == "out_invoice")
        if any(self.env["reza.unable.supply.wizard"]._has_discount(inv) for inv in invoices):
            raise UserError(_("%s was invoiced with a discount. Do this refund by hand.",
                              order.name))

    @api.model
    def _shipping_line(self, order):
        """The paid shipping line still on the order: invoiced and not
        already credited (ordered quantity above zero)."""
        prec = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        return order.order_line.filtered(
            lambda l: l.is_delivery and not l.display_type
            and float_compare(l.product_uom_qty, 0.0, precision_digits=prec) > 0
            and float_compare(l.qty_invoiced, 0.0, precision_digits=prec) > 0
            and not l.currency_id.is_zero(l.price_total))[:1]

    # -------------------------------------------------------------------- log
    def _log(self, order, todo, shipping, refunds, tracked, rows):
        items = Markup("").join(
            Markup("<li>%s × %s</li>") % (wl.qty_to_return, wl.product_id.display_name)
            for wl in todo)
        if shipping:
            items += Markup("<li>%s</li>") % _("Shipping (%s)", format_amount(
                self.env, shipping.price_total, order.currency_id))
        body = Markup("<p><b>%s</b> (%s)</p><ul>%s</ul>") % (_("Refund (shipped)"), self.reason, items)
        body += Markup("<p>%s</p>") % _("Items received back.")
        if not refunds:
            body += Markup("<p>%s</p>") % _(
                "Nothing was invoiced for these items, so there is nothing to refund.")
        for row in tracked:
            amount = format_amount(self.env, row.amount, row.currency_id)
            if row.state == "queued":
                body += Markup("<p><b>%s</b></p>") % _(
                    "%(cn)s: Odoo is sending a refund of %(amt)s to Stripe in the next few minutes. "
                    "This order says when it has gone; the daily check confirms it.",
                    cn=row.credit_note_id._get_html_link(), amt=amount)
            else:
                body += Markup("<p><b>%s</b></p>") % _(
                    "%(cn)s: %(task)s Task given to %(user)s. The daily check confirms the refund.",
                    cn=row.credit_note_id._get_html_link(), task=row._task_text(),
                    user=row.activity_id.user_id.name or _("Accounts"))
            if row.note and row.state != "queued":
                body += Markup("<p>%s</p>") % row.note
        if rows:
            body += Markup("<p>%s</p>") % _(
                "Going back to Edbert: %s. The return and both credit notes are done in the "
                "background; this order says when they are finished.",
                ", ".join(rows.mapped("name")))
        order.message_post(body=body)


class RezRefundShippedWizardLine(models.TransientModel):
    _name = "reza.refund.shipped.wizard.line"
    _description = "Refund (shipped) line"

    wizard_id = fields.Many2one("reza.refund.shipped.wizard", required=True, ondelete="cascade")
    sale_line_id = fields.Many2one("sale.order.line", required=True, readonly=True)
    product_id = fields.Many2one(related="sale_line_id.product_id")
    delivered_qty = fields.Float(related="sale_line_id.qty_delivered",
                                 digits="Product Unit of Measure")
    price_unit = fields.Float(related="sale_line_id.price_unit")
    qty_to_return = fields.Float("Returned", digits="Product Unit of Measure", default=0.0)
