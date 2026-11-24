# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import models
from odoo.fields import Domain


class Website(models.Model):
    _inherit = "website"

    def sale_product_domain(self):
        # Odoo 20 port: get_current_website() is gone. Keep the core domain
        # (sale_ok, published/saleable for non-internal users, company), and
        # swap only core's single-website rule (website_id in [False, current])
        # for this module's multi-website rule, as the 18 override did.
        website = self or self.env.website
        multi_website = Domain("website_ids", "=", False) | Domain("website_ids", "in", website.ids)

        def _swap(condition):
            if condition.field_expr == "website_id":
                return multi_website
            return condition

        return Domain(super().sale_product_domain()).map_conditions(_swap)
