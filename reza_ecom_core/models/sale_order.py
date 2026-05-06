# -- coding: utf-8 --
from odoo import _, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_generate_coupon(self):
        self.ensure_one()

        Wizard = self.env['loyalty.generate.wizard']
        Card = self.env['loyalty.card']
        History = self.env['loyalty.history']

        program = self.website_id.program_coupon_abandoned_cart_email
        if not program:
            return super().action_generate_coupon()

        partner = self.partner_id

        # Only reuse if still valid
        domain = [
            ('program_id', '=', program.id),
            ('partner_id', '=', partner.id),
            ('expiration_date', '>=', fields.Date.context_today(self)),
        ]
        card = Card.search(domain, limit=1)
        if card:
            return card.code

        # Generate fresh coupon
        days = self.website_id.days_coupon_abandoned_cart_email or 2

        wizard_vals = {
            'mode': 'selected',
            'customer_ids': [partner.id],
            'program_id': program.id,
            'coupon_qty': 1,
            'description': _('Gift for Customer'),
            'valid_until': fields.Date.add(fields.Date.context_today(self), days=days),
        }
        wizard = Wizard.create(wizard_vals)

        coupon_vals = wizard._get_coupon_values(partner)
        Card = Card.with_context(action_no_send_mail=True)
        coupon = Card.create(coupon_vals)

        history_vals = {
            'description': wizard.description or _('Gift for Customer'),
            'card_id': coupon.id,
            'issued': wizard.points_granted,
        }
        History.create(history_vals)

        return coupon.code