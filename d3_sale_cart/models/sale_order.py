# -*- coding: utf-8 -*-

from urllib.parse import quote

from odoo import _, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_generate_coupons(self):
        for sale in self.filtered(
            lambda s: s.website_id and s.website_id.create_coupon_abandoned_cart_email
        ):
            sale.action_generate_coupon()
        return True

    def action_generate_coupon(self):
        self.ensure_one()

        Wizard = self.env["loyalty.generate.wizard"]
        Card = self.env["loyalty.card"]
        History = self.env["loyalty.history"]

        # program = self.env.ref("d3_sale_cart.10_percent_coupon")
        program = self.website_id.program_coupon_abandoned_cart_email
        partner = self.partner_id

        # Search first
        domain = [("program_id", "=", program.id), ("partner_id", "=", partner.id)]
        card = Card.search(domain, limit=1)
        if card:
            return card.code

        days = self.website_id.days_coupon_abandoned_cart_email or 2

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
        Card = Card.with_context(action_no_send_mail=True)
        coupon = Card.create(coupon_vals)

        history_vals = {
            "description": wizard.description or _("Gift for Customer"),
            "card_id": coupon.id,
            "issued": wizard.points_granted,
        }
        # Odoo 20: card points are computed from loyalty.history, so this line is
        # what grants the points (18 also wrote `points` on the card). No mail,
        # as on 18 (action_no_send_mail only covers the creation communication).
        History.with_context(loyalty_no_mail=True).create(history_vals)

        return coupon.code

    def _cart_recovery_email_send(self):
        """Odoo 20 abandoned-cart cron (website._cron_send_abandoned_cart_email)
        sends each batch through this method; 18's website._send_abandoned_cart_email
        is gone. Generate the coupon first so the recovery email can show it."""
        for order in self.filtered(
            lambda o: o.website_id.create_coupon_abandoned_cart_email
            and o.website_id.program_coupon_abandoned_cart_email
        ):
            order.sudo().action_generate_coupon()
        return super()._cart_recovery_email_send()

    def action_generate_coupon_cart_recovery_url(self):
        self.ensure_one()

        code = self.action_generate_coupon()
        if not code:
            return self.get_portal_url()

        access_token = self.access_token or self._portal_ensure_token()
        return "%s/d3_sale_cart/recover/%s/%s/%s" % (
            self.get_base_url(),
            self.id,
            quote(access_token, safe=""),
            quote(code, safe=""),
        )
