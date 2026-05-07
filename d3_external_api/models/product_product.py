# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    external_api_id = fields.Integer(string="External API ID", copy=False)

    external_api = fields.Boolean('No Sync', copy=False)
