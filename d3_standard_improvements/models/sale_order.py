# -*- coding: utf-8 -*-


from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    report_product_image = fields.Boolean(
        related="company_id.report_product_image", readonly=True
    )
