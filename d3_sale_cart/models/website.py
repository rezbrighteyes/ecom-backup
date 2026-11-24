# -*- coding: utf-8 -*-

from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    create_coupon_abandoned_cart_email = fields.Boolean()
    days_coupon_abandoned_cart_email = fields.Integer()
    program_coupon_abandoned_cart_email = fields.Many2one("loyalty.program")

