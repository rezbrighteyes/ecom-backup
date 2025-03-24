# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import models, fields


class MassUpdateProductWebsite(models.TransientModel):
    _name = "sh.product.multi.website"
    _description = "Mass Update Product Website"

    website_ids = fields.Many2many("website", string="Websites", required=True)

    def action_update(self):
        active_ids = self.env.context.get("active_ids")
        if active_ids:
            product_ids = self.env["product.template"].sudo().browse(
                active_ids)
            if product_ids:
                for product in product_ids:
                    product.sudo().write({
                        "website_ids": [(6, 0, self.website_ids.ids)]
                    })
