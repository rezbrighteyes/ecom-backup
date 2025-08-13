# -*- coding: utf-8 -*-

from odoo import _, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_generate_coupons(self):
        for sale in self.filtered(
            lambda s: s.company_id.create_coupon_abandoned_cart_email
        ):
            sale.action_generate_coupon()
        return True

    def action_generate_coupon(self):
        self.ensure_one()

        Wizard = self.env["loyalty.generate.wizard"]
        Card = self.env["loyalty.card"]
        History = self.env["loyalty.history"]

        # program = self.env.ref("d3_sale_cart.10_percent_coupon")
        program = self.company_id.program_coupon_abandoned_cart_email
        partner = self.partner_id

        days = self.company_id.days_coupon_abandoned_cart_email or 2

        wizard_vals = {
            "mode": "selected",
            "customer_ids": [partner.id],
            "program_id": program.id,
            "coupon_qty": 1,
            "description": _("Gift for Customer"),
            "valid_until": fields.Date.add(fields.Date.context_today(self), days=days),
        }
        wizard = Wizard.create(wizard_vals)

        coupon_vals = wizard._get_coupon_values(partner)
        coupon = Card.create(coupon_vals)

        history_vals = {
            "description": wizard.description or _("Gift for Customer"),
            "card_id": coupon.id,
            "issued": wizard.points_granted,
        }
        History.create(history_vals)

        return coupon.code
