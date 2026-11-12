# -*- coding: utf-8 -*-
from odoo import _, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _reza_price_list_scope(self):
        """Every active list that can sell these products.

        A product with no company can be on any list. One held by a company
        can be on lists of that company, of its branches, or of no company.
        """
        companies = self.mapped("product_tmpl_id.company_id")
        domain = []
        if companies and all(self.mapped("product_tmpl_id.company_id")):
            branches = self.env["res.company"].sudo().search([("id", "child_of", companies.ids)])
            domain = ["|", ("company_id", "=", False), ("company_id", "in", branches.ids)]
        return self.env["product.pricelist"].search(domain, order="sequence, id")

    def action_reza_price_lists(self):
        """Price Lists: what every list charges for this product, and why.

        The reverse of Check Prices. One check per list over these variants
        only, using the same engine, so category and all-product rules count
        as well as rules aimed at the product itself, and both screens agree.
        """
        products = self.filtered(lambda p: p.sale_ok)
        if not products:
            products = self
        Check = self.env["reza.pricelist.check"]
        checks = Check
        for pricelist in products._reza_price_list_scope():
            check = Check.create({
                "pricelist_id": pricelist.id,
                "company_id": (pricelist.company_id or self.env.company).id,
            })
            check._reza_run(products)
            checks |= check
        name = products.product_tmpl_id.name if len(products.product_tmpl_id) == 1 else _("Products")
        context = {"reza_by_product": True}
        if len(products) > 1:
            context["search_default_groupby_variant"] = 1
        return {
            "type": "ir.actions.act_window",
            "name": _("Price Lists: %s", name),
            "res_model": "reza.pricelist.check.line",
            "view_mode": "list,form",
            "views": [(self.env.ref("reza_pricelist_check.view_reza_pricelist_check_line_by_product").id, "list"),
                      (False, "form")],
            "domain": [("check_id", "in", checks.ids)],
            "context": context,
            "target": "current",
        }


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_reza_price_lists(self):
        self.ensure_one()
        return self.product_variant_ids.action_reza_price_lists()
