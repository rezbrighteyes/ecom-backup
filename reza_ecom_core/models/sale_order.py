# -- coding: utf-8 --
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_generate_coupon(self):
        self.ensure_one()

        Card = self.env['loyalty.card']

        program = self.website_id.program_coupon_abandoned_cart_email
        if not program:
            return super().action_generate_coupon()

        partner = self.partner_id

        domain = [
            ('program_id', '=', program.id),
            ('partner_id', '=', partner.id),
            ('expiration_date', '>=', fields.Date.context_today(self)),
        ]
        card = Card.search(domain, limit=1)
        if card:
            return card.code

        return super().action_generate_coupon()
