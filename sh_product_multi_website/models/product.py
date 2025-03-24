# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = "product.template"

    website_ids = fields.Many2many("website", string="Websites")


class Product(models.Model):
    _inherit = "product.product"

    website_ids = fields.Many2many(
        related="product_tmpl_id.website_ids", readonly=False)
