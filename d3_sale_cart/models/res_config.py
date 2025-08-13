# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    create_coupon_abandoned_cart_email = fields.Boolean(
        related="company_id.create_coupon_abandoned_cart_email",
        readonly=False
    )
    days_coupon_abandoned_cart_email = fields.Integer(
        related="company_id.days_coupon_abandoned_cart_email",
        readonly=False
    )
    program_coupon_abandoned_cart_email = fields.Many2one(
        related="company_id.program_coupon_abandoned_cart_email",
        readonly=False
    )
