# -*- coding: utf-8 -*-

from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    create_coupon_abandoned_cart_email = fields.Boolean()
    days_coupon_abandoned_cart_email = fields.Integer()
    program_coupon_abandoned_cart_email = fields.Many2one("loyalty.program")


    def _send_abandoned_cart_email(self):
        for website in self.search([]):
            if not website.send_abandoned_cart_email:
                continue
            if not website.create_coupon_abandoned_cart_email:
                continue
            if not website.program_coupon_abandoned_cart_email:
                continue
            abandoned_carts = self.env['sale.order'].search([
                ('is_abandoned_cart', '=', True),
                ('cart_recovery_email_sent', '=', False),
                ('website_id', '=', website.id),
            ])
            #raise UserError(abandoned_carts)
            for order in abandoned_carts:
                order.sudo().action_generate_coupon()
        super()._send_abandoned_cart_email()