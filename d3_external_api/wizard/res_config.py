# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    external_api = fields.Boolean(related="company_id.external_api", readonly=False)

    external_api_url = fields.Char(
        related="company_id.external_api_url", readonly=False
    )
    external_api_db = fields.Char(related="company_id.external_api_db", readonly=False)
    external_api_username = fields.Char(
        related="company_id.external_api_username", readonly=False
    )
    external_api_password = fields.Char(
        related="company_id.external_api_password", readonly=False
    )

    # Product
    external_api_product = fields.Boolean(
        related="company_id.external_api_product", readonly=False
    )

    # Purchase
    external_api_purchase = fields.Boolean(
        related="company_id.external_api_purchase", readonly=False
    )
    external_api_purchase_partner = fields.Integer(
        related="company_id.external_api_purchase_partner", readonly=False
    )

    # Quant
    external_api_quant = fields.Boolean(
        related="company_id.external_api_quant", readonly=False
    )
    external_api_location_id = fields.Many2one(
        related="company_id.external_api_location_id", readonly=False
    )
    external_api_partner_id = fields.Many2one(
        related="company_id.external_api_partner_id", readonly=False
    )
