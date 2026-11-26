# -*- coding: utf-8 -*-
"""Featured brand tiles of the storefront's Brands menu, per website, in order.

Access (security/): website designers only. Nothing for other internal,
portal or public users: the storefront reaches these rows only through the
gated menu export (menu.py), which runs them through sudo() and writes out
id, name and slug of brands that have a published product on that website.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StorefrontFeaturedBrand(models.Model):
    _name = "reza.storefront.featured.brand"
    _description = "Storefront featured brand"
    _order = "website_id, sequence, id"

    website_id = fields.Many2one("website", required=True, ondelete="cascade", index=True)
    brand_id = fields.Many2one("product.data.feed.brand", string="Brand", required=True,
                               ondelete="cascade")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.constrains("website_id", "brand_id")
    def _check_unique(self):
        for row in self:
            if self.with_context(active_test=False).search_count([
                    ("website_id", "=", row.website_id.id), ("brand_id", "=", row.brand_id.id),
                    ("id", "!=", row.id)]):
                raise ValidationError(_("%s is already a featured brand of this website.",
                                        row.brand_id.name))
