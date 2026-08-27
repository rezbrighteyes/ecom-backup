import logging
from odoo import models

_logger = logging.getLogger(__name__)


class ProductTemplateSitemap(models.Model):
    _inherit = 'product.template'

    def _get_sitemap_urls(self, query_string=None, canonical_params=None):
        """Product entries for the sitemap, one website at a time.

        Two defects this method used to carry:

        - It emitted '/shop/<seo_name>'. seo_name is not a URL — Odoo routes on
          '<slug>-<id>' and 404s without the id — so every entry pointed at a
          404. website_url is the value the canonical tag uses.
        - It searched every published product in the database. public catalogues
          are scoped per website through website_ids, so an unscoped search puts
          all seven storefronts' products into each one's sitemap.

        Note: this override appears to be unreachable. Odoo builds the shop
        sitemap from the website_sale controller's sitemap_shop generator, and
        no product.template in this codebase or in core defines
        _get_sitemap_urls — so the super() call below would raise. The live
        sitemap confirms it: it carries the '<slug>-<id>' form this method never
        produced, and a lastmod on three URLs where this method sets one on
        every product. Fixed rather than deleted so it is correct if something
        does reach it; verify on staging, then delete it.
        """
        try:
            root = super()._get_sitemap_urls(query_string, canonical_params)
        except AttributeError:
            root = []

        domain = [('website_published', '=', True), ('sale_ok', '=', True)]
        try:
            website = self.env['website'].get_current_website()
            if website:
                domain.append(('website_ids', 'in', website.ids))
        except Exception:
            _logger.warning('Sitemap: no current website, falling back to every published product')

        published = self.env['product.template'].sudo().search(domain)

        result = list(root)
        for product in published:
            try:
                result.append({
                    'loc': product.website_url,
                    'priority': 1.0 if product._is_in_stock() else 0.1,
                    'lastmod': product.write_date.strftime('%Y-%m-%d'),
                })
            except Exception as e:
                _logger.warning('Sitemap error for product %s: %s', product.id, e)

        return result
