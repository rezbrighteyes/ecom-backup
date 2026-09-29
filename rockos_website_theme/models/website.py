from odoo import api, fields, models


class Website(models.Model):
    _inherit = "website"

    rockos_facebook_url = fields.Char(string="Rockos Facebook URL")
    rockos_instagram_url = fields.Char(string="Rockos Instagram URL")
    rockos_phone = fields.Char(string="Rockos Phone")
    rockos_free_shipping_text = fields.Char(string="Rockos Free Shipping Text")
    rockos_hero_image = fields.Binary(
        string="Homepage Hero Banner",
        attachment=True,
    )
    rockos_best_seller_product_ids = fields.Many2many(
        "product.template",
        "rockos_website_best_seller_rel",
        "website_id",
        "product_tmpl_id",
        string="Homepage Best Sellers",
    )
    rockos_new_arrival_product_ids = fields.Many2many(
        "product.template",
        "rockos_website_new_arrival_rel",
        "website_id",
        "product_tmpl_id",
        string="Homepage New Arrivals",
    )

    def _rockos_category(self, name, parent_name=None):
        """This website's eCommerce category with the given name, or empty."""
        self.ensure_one()
        domain = [("website_id", "=", self.id), ("name", "=", name)]
        if parent_name:
            domain.append(("parent_id.name", "=", parent_name))
        return self.env["product.public.category"].sudo().search(domain, limit=1)

    def _rockos_category_url(self, name, parent_name=None, search=None):
        """Link to a category page. Falls back to a shop search if the
        category has not been created on this website yet."""
        category = self._rockos_category(name, parent_name)
        if category:
            return self._rockos_category_href(category)
        return "/shop?search=%s" % (search or name).replace(" ", "+")

    def _rockos_category_href(self, category):
        return "/shop/category/%s" % self.env["ir.http"]._slug(category)

    def _rockos_top_categories(self):
        self.ensure_one()
        return self.env["product.public.category"].sudo().search(
            [("website_id", "=", self.id), ("parent_id", "=", False)],
            order="sequence, id",
        )

    def _rockos_visible_products(self, products):
        """Drop homepage picks that this website would not show."""
        self.ensure_one()
        return products.filtered(
            lambda p: p.active and p.is_published and p.sale_ok
            and (not p.website_ids or self in p.website_ids)
        )

    @api.model
    def _rockos_setup_menu(self):
        from ..hooks import _scope_views_to_rockos, _seed_rockos_menu, _setup_rockos_pages

        website = self.sudo().search([("name", "=", "Rockos")], limit=1)
        if website:
            _scope_views_to_rockos(self.env, website)
            _seed_rockos_menu(self.env, website)
            _setup_rockos_pages(self.env, website)
        return True
