# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import models, fields
from odoo.exceptions import AccessError


class MassUpdateProductWebsite(models.TransientModel):
    _name = "sh.product.multi.website"
    _description = "Mass Update Product Website"

    website_ids = fields.Many2many("website", string="Websites", required=True)

    def action_update(self):
        # Writes under sudo, and a public method is callable over RPC by any
        # signed-in user (portal shoppers included): only product editors.
        if not self.env.su and not self.env.user.has_group("product.group_product_manager") \
                and not self.env.user.has_group("base.group_system"):
            raise AccessError(self.env._("Only product managers can change product websites."))
        active_ids = self.env.context.get("active_ids")
        if active_ids:
            product_ids = self.env["product.template"].sudo().browse(
                active_ids)
            if product_ids:
                for product in product_ids:
                    product.sudo().write({
                        "website_ids": [(6, 0, self.website_ids.ids)]
                    })
