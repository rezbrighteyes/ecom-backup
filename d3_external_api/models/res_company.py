# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.Model):
    _inherit = "res.company"

    def _default_external_api_location_id(self):
        warehouse = self.env.ref("d3_external_api.warehouse_external_api", raise_if_not_found=False)
        if warehouse:
            return warehouse.lot_stock_id
        else:
            return False

    # External API
    external_api = fields.Boolean()

    external_api_url = fields.Char(string="External API URL")
    external_api_db = fields.Char(string="External API DB")
    external_api_username = fields.Char(string="External API Username")
    external_api_password = fields.Char(string="External API Password")

    # Product
    external_api_product = fields.Boolean()

    # Purchase
    external_api_purchase = fields.Boolean()
    external_api_purchase_partner = fields.Integer()

    # Quant
    external_api_quant = fields.Boolean()
    external_api_location_id = fields.Many2one(
        "stock.location", default=_default_external_api_location_id
    )
    external_api_partner_id = fields.Many2one("res.partner")
