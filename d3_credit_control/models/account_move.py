# -*- coding: utf-8 -*-

from odoo import models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        invoices = self.filtered(lambda i: i.move_type == "out_invoice")
        for invoice in invoices:
            if (
                invoice.partner_id.commercial_partner_id.credit_control
                and invoice.partner_credit_warning
            ):
                raise UserError("Customer is blocked due to credit limit.")
            if (
                invoice.partner_id.commercial_partner_id.overdue_control
                and invoice.partner_id.commercial_partner_id.credit_due
            ):
                raise UserError("Customer is blocked due to overdue invoices.")
        return super(AccountMove, self).action_post()
