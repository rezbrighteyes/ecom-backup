# -*- coding: utf-8 -*-

from odoo import fields, models


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    hide_payment_if_over_credit = fields.Boolean()

    def _get_compatible_providers(self, company_id, partner_id, amount, currency_id=None, force_tokenization=False,
        is_express_checkout=False, is_validation=False, **kwargs):
        compatible_providers = super()._get_compatible_providers(company_id, partner_id, amount, currency_id=currency_id, force_tokenization=force_tokenization,
        is_express_checkout=is_express_checkout, is_validation=is_validation, **kwargs)

        sale_order_id = kwargs.get('sale_order_id')
        if sale_order_id:
            sale_order = self.env['sale.order'].browse(kwargs['sale_order_id'])
            if sale_order and sale_order.company_id.account_use_credit_limit:
                current_amount=(sale_order.amount_total / sale_order.currency_rate)
                partner_id = sale_order.partner_id.commercial_partner_id
                credit_to_invoice = partner_id.credit_to_invoice
                total_credit = partner_id.credit + credit_to_invoice + current_amount

                if partner_id.credit_limit and total_credit > partner_id.credit_limit:
                    compatible_providers = compatible_providers.filtered(lambda x: not x.hide_payment_if_over_credit)

        return compatible_providers