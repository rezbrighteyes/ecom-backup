# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    create_coupon_abandoned_cart_email = fields.Boolean()
    days_coupon_abandoned_cart_email = fields.Integer()
    program_coupon_abandoned_cart_email = fields.Many2one("loyalty.program")
