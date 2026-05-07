# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.depends("company_id", "partner_id", "amount_total")
    def _compute_partner_credit_warning(self):
        for order in self:
            order.with_company(order.company_id)
            order.partner_credit_warning = ""
            show_warning = (
                order.state in ("draft", "sent")
                and order.company_id.account_use_credit_limit
            )
            if show_warning:
                orders = (
                    self.partner_id.commercial_partner_id.sale_order_ids.filtered(
                        lambda s: s.state in ("draft", "sent")
                        and s.invoice_status in ("no", "to invoice")
                    )
                    | order
                )
                current_amount = sum([o.amount_total / o.currency_rate for o in orders])
                order.partner_credit_warning = self.env[
                    "account.move"
                ]._build_credit_warning_message(
                    order.sudo(),  # ensure access to `credit` & `credit_limit` fields
                    current_amount=current_amount,
                )

    def action_confirm(self):
        for order in self:
            if (
                order.partner_id.commercial_partner_id.credit_control
                and order.partner_credit_warning
            ):
                raise UserError("Customer is blocked due to credit limit.")
            if (
                order.partner_id.commercial_partner_id.overdue_control
                and order.partner_id.commercial_partner_id.credit_due
            ):
                raise UserError("Customer is blocked due to overdue invoices.")
        return super(SaleOrder, self).action_confirm()
