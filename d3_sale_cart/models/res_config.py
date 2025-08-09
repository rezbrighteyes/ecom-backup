# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    create_coupon_abandoned_cart_email = fields.Boolean(
        related="company_id.create_coupon_abandoned_cart_email",
        readonly=False
    )
