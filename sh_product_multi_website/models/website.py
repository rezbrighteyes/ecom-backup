# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import models

class Website(models.Model):
    _inherit = "website"

    def sale_product_domain(self):
        return [("sale_ok", "=", True)] + [
            "|",
            ("website_ids", "=", False),
            ("website_ids", "in", self.get_current_website().ids)]
