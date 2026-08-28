import json
import logging

from markupsafe import Markup
from odoo import api, models

from .product_template import _slug_record

_logger = logging.getLogger(__name__)

MAX_META_TITLE = 60
MAX_META_DESCRIPTION = 158


class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    # -- helpers -----------------------------------------------------------

    def _get_seo_param(self, key, default=''):
        try:
            return self.env['ir.config_parameter'].sudo().get_param(
                'rezads_seo.%s' % key, default
            )
        except Exception:
            return default

    def _seo_feature_enabled(self, feature):
        return self._get_seo_param('enable_%s' % feature, 'True') == 'True'

    def _seo_website(self):
        """The website this category belongs to, else the current one."""
        self.ensure_one()
        if self.website_id:
            return self.website_id
        try:
            return self.env['website'].get_current_website()
        except Exception:
            return self.env['website'].browse()

    def _seo_published_products(self):
        """Published products in this category and its children.

        Counted through parents_and_self on the product side so a parent
        category ('Apparel') reflects everything beneath it rather than only
        the handful assigned to the parent node directly.
        """
        self.ensure_one()
        descendants = self.search([('id', 'child_of', self.id)])
        return self.env['product.template'].sudo().search([
            ('public_categ_ids', 'in', descendants.ids),
            ('is_published', '=', True),
            ('sale_ok', '=', True),
        ])

    # -- meta generation ---------------------------------------------------

    def _build_category_meta_title(self):
        """'<Category> | <Website>', trimmed to the display cut.

        Deliberately plainer than the product title generator: a category name
        is already the search term, so there is nothing to compress or reorder.
        """
        self.ensure_one()
        website = self._seo_website()
        brand = website.name or ''
        name = (self.name or '').strip()
        if not name:
            return ''
        title = '%s | %s' % (name, brand) if brand else name
        if len(title) <= MAX_META_TITLE:
            return title
        return name[:MAX_META_TITLE].rstrip(' -|')

    def _build_category_meta_description(self):
        """A description built from what the category actually contains.

        22 of 24 category pages shipped with no meta description at all, so
        Google wrote its own snippet out of the product grid. Product count and
        price floor are the two facts a shopper scanning a SERP acts on, so
        they carry the sentence. Returns '' when the category is empty rather
        than advertising a page with nothing on it.
        """
        self.ensure_one()
        name = (self.name or '').strip()
        if not name:
            return ''

        products = self._seo_published_products()
        count = len(products)
        if not count:
            return ''

        website = self._seo_website()
        brand = website.name or ''
        currency = website.currency_id.name if website.currency_id else 'AUD'
        symbol = '$' if currency in ('AUD', 'USD', 'NZD') else ''

        prices = [p.list_price for p in products if p.list_price]

        # Not "Shop 105 toys products". Category names are frequently already
        # plural (Toys, Sunglasses) or uncountable (Apparel), so appending a
        # noun to them produces copy no one would write by hand. Naming the
        # range and counting separately reads correctly whatever the category
        # is called.
        if brand:
            opening = 'Shop the %s range at %s' % (name, brand)
        else:
            opening = 'Shop the %s range' % name
        parts = ['%s — %d product%s' % (opening, count, '' if count == 1 else 's')]

        if prices:
            parts[0] += ' from %s%.2f' % (symbol, min(prices))
        parts[0] += '.'

        threshold = self._get_seo_param('free_shipping_threshold', '')
        if threshold:
            try:
                parts.append('Free shipping over %s%d.' % (symbol, int(float(threshold))))
            except (TypeError, ValueError):
                pass

        description = ' '.join(parts)
        if len(description) <= MAX_META_DESCRIPTION:
            return description
        trimmed = description[:MAX_META_DESCRIPTION]
        return trimmed[:trimmed.rfind(' ')].rstrip(' .,') + '.'

    def _set_category_seo_defaults(self, name_changed=False):
        """Fill empty meta fields; never overwrite copy someone wrote by hand.

        Two categories on WhatYouNeed carry hand-written descriptions that
        outperform anything generated here, so an existing value always wins
        unless the category was renamed.
        """
        for record in self:
            updates = {}
            try:
                if self._seo_feature_enabled('auto_title'):
                    if not record.website_meta_title or name_changed:
                        title = record._build_category_meta_title()
                        if title:
                            updates['website_meta_title'] = title

                if self._seo_feature_enabled('auto_description'):
                    if not record.website_meta_description:
                        description = record._build_category_meta_description()
                        if description:
                            updates['website_meta_description'] = description

                if updates:
                    super(ProductPublicCategory, record).write(updates)
            except Exception as e:
                _logger.error(
                    'Category SEO defaults failed for %s (id=%s): %s',
                    record.name, record.id, e,
                )

    # -- hooks -------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._set_category_seo_defaults()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            self._set_category_seo_defaults(name_changed=True)
        return res

    # -- schema ------------------------------------------------------------

    def _seo_ancestors(self):
        """Root-first ancestor chain, stopping at a website boundary.

        Same defect the product breadcrumb carried: category trees cross
        websites in this database, and walking parent_id blindly emits a URL
        that 404s on the current domain.
        """
        self.ensure_one()
        website = self._seo_website()
        chain, node = [], self
        while node:
            if website and node.website_id and node.website_id.id != website.id:
                break
            chain.insert(0, node)
            node = node.parent_id
        return chain

    def get_category_jsonld(self, products=None):
        """CollectionPage + BreadcrumbList + ItemList for a category page.

        Category pages carried no structured data of any kind, while being the
        pages most likely to earn a head term. The ItemList names the products
        actually rendered on this page — not the whole category — so the markup
        describes what a visitor to this URL sees.
        """
        self.ensure_one()
        if not self._seo_feature_enabled('category_schema'):
            return Markup('')
        try:
            website = self._seo_website()
            base = website._seo_base_url() if website else ''

            def _url(path):
                return '%s%s' % (base, path) if base else path

            category_path = '/shop/category/%s' % _slug_record(self)

            crumbs = [{
                '@type': 'ListItem',
                'position': 1,
                'name': website.name if website else 'Home',
                'item': _url('/'),
            }, {
                '@type': 'ListItem',
                'position': 2,
                'name': 'Shop',
                'item': _url('/shop'),
            }]
            for ancestor in self._seo_ancestors():
                crumbs.append({
                    '@type': 'ListItem',
                    'position': len(crumbs) + 1,
                    'name': ancestor.name or '',
                    'item': _url('/shop/category/%s' % _slug_record(ancestor)),
                })

            elements = []
            for position, product in enumerate(products or self.env['product.template'], start=1):
                elements.append({
                    '@type': 'ListItem',
                    'position': position,
                    'name': product.name or '',
                    'url': _url(product.website_url or ''),
                })

            collection = {
                '@type': 'CollectionPage',
                'name': self.website_meta_title or self.name or '',
                'url': _url(category_path),
            }
            description = self.website_meta_description
            if description:
                collection['description'] = description
            if elements:
                collection['mainEntity'] = {
                    '@type': 'ItemList',
                    'numberOfItems': len(elements),
                    'itemListElement': elements,
                }

            data = {
                '@context': 'https://schema.org/',
                '@graph': [
                    collection,
                    {'@type': 'BreadcrumbList', 'itemListElement': crumbs},
                ],
            }
            return Markup(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            _logger.error(
                'Category JSON-LD error for %s (id=%s): %s', self.name, self.id, e
            )
            return Markup('')
