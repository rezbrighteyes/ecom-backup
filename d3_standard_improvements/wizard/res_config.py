# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    report_product_image = fields.Boolean(
        related="company_id.report_product_image", readonly=False
    )
    work_center_cost = fields.Boolean(
        related="company_id.work_center_cost", readonly=False
    )
