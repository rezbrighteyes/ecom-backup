# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    create_coupon_abandoned_cart_email = fields.Boolean()
