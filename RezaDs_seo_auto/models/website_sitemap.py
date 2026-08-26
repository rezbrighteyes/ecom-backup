import logging
from odoo import models

from .product_template import _make_slug

_logger = logging.getLogger(__name__)


class ProductTemplateSitemap(models.Model):
    _inherit = 'product.template'

    def _get_sitemap_urls(self, query_string=None, canonical_params=None):
        root = super()._get_sitemap_urls(query_string, canonical_params)

        published = self.env['product.template'].sudo().search([
            ('website_published', '=', True),
            ('sale_ok', '=', True),
        ])

        result = []
        for product in published:
            try:
                if product._is_in_stock():
                    priority = 1.0
                else:
                    priority = 0.1

                # Fall back to a sanitised slug plus the id. The raw name put an
                # unescaped string into the URL; the id keeps it resolvable the
                # way Odoo's own /shop/<slug>-<id> is.
                slug = product.seo_name or '%s-%s' % (_make_slug(product.name or ''), product.id)
                result.append({
                    'loc': '/shop/%s' % slug,
                    'priority': priority,
                    'lastmod': product.write_date.strftime('%Y-%m-%d'),
                })
            except Exception as e:
                _logger.warning('Sitemap error for product %s: %s', product.id, e)

        return result
