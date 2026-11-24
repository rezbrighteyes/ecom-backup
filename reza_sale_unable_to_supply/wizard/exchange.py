# -*- coding: utf-8 -*-
"""Exchange: swap an item on a confirmed order for another one, before it ships.

It is Cannot Supply for the old item, plus a new order line for the new one,
in one transaction. The old item comes off the order and the delivery, and
whatever of it was invoiced is credited (the Cannot Supply code does all of
that). The new item goes on as a normal order line, so sale_stock adds it to
the open delivery and the Edbert bridge later buys what actually shipped.

Price rule (Rez, 2026-10-08): if the new line differs from what the customer
paid for the old one by less than $1.00, the customer keeps the price they
paid. Otherwise the new price stands, and the difference is either owed by the
customer or refunded to them.

Money. When the old item was invoiced, the new line is invoiced at once and
the credit note is matched against THAT new invoice, not the original one.
Odoo matches a credit note to the invoice it reverses on posting
(`_reconcile_reversed_moves`); left like that, on Rockos (payments without a
journal entry) the original would look part-paid and the new invoice unpaid,
although the customer paid everything. Re-matching to the new invoice leaves:
same price -> credit note and new invoice both Paid; dearer -> the new invoice
shows the amount the customer owes; cheaper -> the credit note shows the amount
to refund.

After-delivery exchanges are NOT handled here: the Edbert bridge buys from
Edbert once per order, so a replacement shipped after the first purchase would
never be bought. That needs a decision first.
"""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import float_compare, format_amount

KEEP_PRICE_BELOW = 1.00  # dollars, on the line total


class RezExchangeWizard(models.TransientModel):
    _name = "reza.exchange.wizard"
    _description = "Exchange"

    order_id = fields.Many2one("sale.order", required=True, readonly=True, ondelete="cascade")
    line_ids = fields.One2many("reza.exchange.wizard.line", "wizard_id")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env["sale.order"].browse(res.get("order_id") or self.env.context.get("default_order_id"))
        if order and "line_ids" in fields_list:
            res["line_ids"] = [
                Command.create({"sale_line_id": line.id})
                for line in order.order_line
                if not line.display_type and not line.is_downpayment
                and line.product_id.type == "consu"
                and not ("is_reward_line" in line._fields and line.is_reward_line)
            ]
        return res

    def action_apply(self):
        """Button target, so it must stay public. Rights are re-checked in
        the Cannot Supply step it runs."""
        self.ensure_one()
        order = self.order_id
        prec = self.env["decimal.precision"].precision_get("Product Unit")
        todo = self.line_ids.filtered(
            lambda wl: float_compare(wl.qty_to_exchange, 0.0, precision_digits=prec) > 0)
        remover = self.env["reza.unable.supply.wizard"].create({
            "order_id": order.id,
            "reason": _("Exchange"),
            "line_ids": [Command.create({"sale_line_id": wl.sale_line_id.id,
                                         "qty_to_remove": wl.qty_to_exchange}) for wl in todo],
        })
        remover._check_rights()
        self._check_can_exchange(order, todo)

        # What the customer paid for the old items, read before they change.
        paid = {wl: wl.sale_line_id.price_reduce_taxinc * wl.qty_to_exchange for wl in todo}

        removed, refunds = remover._remove_and_credit()

        new_lines = self.env["sale.order.line"]
        kept = {}
        for wl in todo:
            old = wl.sale_line_id
            new = self.env["sale.order.line"].create({
                "order_id": order.id,
                "product_id": wl.new_product_id.id,
                "product_uom_qty": wl.qty_to_exchange,
                "sequence": old.sequence,
            })
            diff = new.price_total - paid[wl]
            kept[wl] = abs(diff) < KEEP_PRICE_BELOW
            if kept[wl]:
                new.write({"price_unit": old.price_unit, "discount": old.discount,
                           "tax_ids": [Command.set(old.tax_ids.ids)]})
            new_lines |= new

        invoice = self.env["account.move"]
        if refunds:
            invoice = order._create_invoices()
            invoice.action_post()
            self._rematch(refunds, invoice)

        self._log(order, todo, new_lines, kept, paid, refunds, invoice)
        return {"type": "ir.actions.act_window_close"}

    def _check_can_exchange(self, order, todo):
        if not todo:
            raise UserError(_("Enter the quantity to exchange on at least one line."))
        for wl in todo:
            if not wl.new_product_id:
                raise UserError(_("Choose the new product for %s.", wl.product_id.display_name))
            if wl.new_product_id == wl.product_id:
                raise UserError(_("%s is the same product. Choose a different one.",
                                  wl.product_id.display_name))
        prec = self.env["decimal.precision"].precision_get("Product Unit")
        invoiced = todo.filtered(
            lambda wl: float_compare(wl.sale_line_id.qty_invoiced, 0.0, precision_digits=prec) > 0)
        if not invoiced:
            return
        # From here the old item was invoiced, so the new one is invoiced at
        # once. That needs an "invoice what is ordered" product ...
        late = invoiced.new_product_id.filtered(lambda p: p.invoice_policy != "order")
        if late:
            raise UserError(_("%s is invoiced on delivery, so it cannot be exchanged here.",
                              ", ".join(late.mapped("display_name"))))
        # ... and an invoice that holds only the new lines. Anything else
        # waiting to be invoiced would be swept into it.
        waiting = order.order_line.filtered(
            lambda l: not l.display_type
            and float_compare(l.qty_to_invoice, 0.0, precision_digits=prec) != 0)
        if waiting:
            raise UserError(_(
                "%(so)s has lines still waiting to be invoiced (%(lines)s). Invoice or fix them first.",
                so=order.name, lines=", ".join(waiting.mapped("product_id.display_name"))))
        # A discount line on an invoice makes the credit note a draft for a
        # person to check, and an exchange cannot match a draft.
        invoices = order.invoice_ids.filtered(lambda m: m.state == "posted" and m.move_type == "out_invoice")
        if any(self.env["reza.unable.supply.wizard"]._has_discount(inv) for inv in invoices):
            raise UserError(_("%s was invoiced with a discount. Do this exchange by hand.", order.name))

    @api.model
    def _rematch(self, refunds, invoice):
        receivable = lambda moves: moves.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled)
        refunds.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable").remove_move_reconcile()
        (receivable(refunds) | receivable(invoice)).reconcile()

    def _log(self, order, todo, new_lines, kept, paid, refunds, invoice):
        items = Markup("").join(
            Markup("<li>%s × %s → %s%s</li>") % (
                wl.qty_to_exchange, wl.product_id.display_name, wl.new_product_id.display_name,
                _(" (price kept)") if kept[wl] else "")
            for wl in todo
        )
        body = Markup("<p><b>%s</b></p><ul>%s</ul>") % (_("Exchange"), items)
        # Odoo never adds a move to a delivery that has been printed
        # (stock_move.py:1359 `printed = False`): the picker may hold the
        # paper. The new item then gets its own delivery, which must be said.
        new_pickings = new_lines.move_ids.picking_id
        other = new_pickings - todo.sale_line_id.move_ids.picking_id
        if other:
            body += Markup("<p><b>%s</b></p>") % _(
                "The new item is on a separate delivery: %s. The first one was already printed. "
                "Ship both, or move the item across before packing.",
                Markup(", ").join(p._get_html_link() for p in other))
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
            change = sum(new_lines.mapped("price_total")) - sum(paid.values())
            if not currency.is_zero(change):
                body += Markup("<p><b>%s</b></p>") % _(
                    "Nothing was invoiced yet. The order total changed by %s.",
                    format_amount(self.env, change, currency))
        order.message_post(body=body)


class RezExchangeWizardLine(models.TransientModel):
    _name = "reza.exchange.wizard.line"
    _description = "Exchange line"

    wizard_id = fields.Many2one("reza.exchange.wizard", required=True, ondelete="cascade")
    sale_line_id = fields.Many2one("sale.order.line", required=True, readonly=True)
    product_id = fields.Many2one(related="sale_line_id.product_id")
    product_tmpl_id = fields.Many2one(related="sale_line_id.product_id.product_tmpl_id")
    ordered_qty = fields.Float(related="sale_line_id.product_uom_qty", digits="Product Unit")
    delivered_qty = fields.Float(related="sale_line_id.qty_delivered", digits="Product Unit")
    price_unit = fields.Float(related="sale_line_id.price_unit")
    qty_to_exchange = fields.Float("Exchange", digits="Product Unit", default=0.0)
    new_product_id = fields.Many2one(
        "product.product", string="New product",
        domain="[('sale_ok', '=', True), ('type', '=', 'consu')]")
