# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.osv import expression


class ProductTemplate(models.Model):
    _inherit = "product.template"

    second_reference = fields.Char(
        compute="_compute_second_reference",
        inverse="_set_second_reference",
        store=True,
    )

    @api.depends("product_variant_ids.second_reference")
    def _compute_second_reference(self):
        self._compute_template_field_from_variant_field("second_reference")

    def _set_second_reference(self):
        self._set_product_variant_field("second_reference")

    @api.model
    def name_search(self, name, args=None, operator="ilike", limit=100):
        res = super().name_search(name, args=args, operator=operator, limit=limit)
        # return res
        res_ids_len = len(res)
        if not name and limit or res_ids_len >= limit:
            return res
        limit -= res_ids_len
        match_domain = [("product_variant_ids.second_reference", operator, name)]
        products = self.search_fetch(
            expression.AND([args or [], match_domain]), ["display_name"], limit=limit
        )
        return res + [(product.id, product.display_name) for product in products.sudo()]

    @api.depends("name", "default_code", "second_reference")
    def _compute_display_name(self):
        for template in self:
            template.display_name = (
                False
                if not template.name
                else (
                    "{}{}{}".format(
                        template.default_code and "[%s] " % template.default_code or "",
                        template.second_reference and "[%s] " % template.second_reference or "",
                        template.name,
                    )
                )
            )
