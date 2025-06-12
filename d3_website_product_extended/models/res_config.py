# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    consider_all_related_warehouses = fields.Boolean(
        related="website_id.consider_all_related_warehouses", readonly=False
    )
