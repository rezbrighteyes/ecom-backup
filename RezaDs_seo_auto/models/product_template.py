import re
import json
import logging
import unicodedata
from datetime import date, timedelta
from markupsafe import Markup
from odoo import api, models

_logger = logging.getLogger(__name__)

STOP_WORDS = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}


def _make_slug(name):
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'[^\w\s-]', '', name).strip().lower()
    words = [w for w in name.split() if w not in STOP_WORDS]
    return re.sub(r'[\s_-]+', '-', ' '.join(words))


def _extract_seo_description(html, max_chars=160):
    if not html:
        return None
    text = re.sub(r'</(h[1-6]|p|div|li)>', '. ', html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\.\s*\.', '.', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) < 30:
        return None
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result = ""
    for sentence in sentences:
        if not result and len(sentence) < 20:
            continue
        candidate = (result + " " + sentence).strip() if result else sentence
        if len(candidate) <= max_chars:
            result = candidate
        else:
            break
    if len(result) >= 50:
        return result
    trimmed = text[:max_chars]
    last_space = trimmed.rfind(' ')
    return (trimmed[:last_space] + '...').strip() if last_space > 0 else trimmed


def _strip_html(html):
    if not html:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._set_seo_defaults()
        return records

    def write(self, vals):
        old_slugs = {}
        if 'name' in vals:
            for record in self:
                if record.seo_name:
                    old_slugs[record.id] = record.seo_name

        res = super().write(vals)

        if any(f in vals for f in ('name', 'description_ecommerce', 'feed_brand_id', 'tag_ids')):
            self._set_seo_defaults(
                name_changed='name' in vals,
                desc_changed='description_ecommerce' in vals,
            )

        if old_slugs:
            for record in self:
                old_slug = old_slugs.get(record.id)
                if old_slug and record.seo_name and old_slug != record.seo_name:
                    record._create_seo_redirect(old_slug)

        return res

    def _create_seo_redirect(self, old_slug):
        self.ensure_one()
        try:
            old_url = '/shop/%s' % old_slug
            new_url = '/shop/%s' % self.seo_name
            existing = self.env['website.rewrite'].sudo().search([
                ('url_from', '=', old_url),
            ], limit=1)
            if not existing:
                self.env['website.rewrite'].sudo().create({
                    'name': 'SEO Redirect: %s' % self.name,
                    'url_from': old_url,
                    'url_to': new_url,
                    'redirect_type': '301',
                })
                _logger.info('301 redirect created: %s -> %s', old_url, new_url)
        except Exception as e:
            _logger.warning('Could not create 301 redirect for %s: %s', self.name, e)

    def _set_seo_defaults(self, name_changed=False, desc_changed=False):
        for record in self:
            updates = {}

            if not record.website_meta_title or name_changed:
                name_part = record.name[:35] if len(record.name) > 35 else record.name
                title = '%s | Buy Online' % name_part
                if len(title) <= 60:
                    try:
                        website = record.env['website'].get_current_website()
                        store_name = website.name if website else ''
                    except Exception:
                        store_name = ''
                    if store_name and len(title) + len(store_name) + 3 <= 60:
                        title = '%s | %s' % (title, store_name)
                updates['website_meta_title'] = title[:60]

            if not record.seo_name or name_changed:
                updates['seo_name'] = _make_slug(record.name)

            if not record.website_meta_description or desc_changed:
                desc = _extract_seo_description(record.description_ecommerce)
                if desc:
                    updates['website_meta_description'] = desc

            if not record.website_meta_keywords or name_changed:
                keywords = []
                if getattr(record, 'feed_brand_id', False) and record.feed_brand_id:
                    keywords.append(record.feed_brand_id.name)
                if record.categ_id:
                    keywords.append(record.categ_id.name)
                if getattr(record, 'tag_ids', False):
                    keywords += record.tag_ids.mapped('name')
                keywords.append(record.name)
                updates['website_meta_keywords'] = ', '.join(keywords)

            if updates:
                super(ProductTemplate, record).write(updates)

    def _is_in_stock(self):
        self.ensure_one()
        product_sudo = self.sudo()
        if getattr(product_sudo, 'allow_out_of_stock_order', False):
            return True
        variant_ids = product_sudo.product_variant_ids.ids
        if not variant_ids:
            return False
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', 'in', variant_ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ])
        return sum(quants.mapped('quantity')) > 0

    def get_schema_jsonld(self, website_name=''):
        self.ensure_one()
        try:
            try:
                website = self.env['website'].get_current_website()
                domain = website.domain or ''
                if domain and not domain.startswith('http'):
                    domain = 'https://%s' % domain
                domain = domain.rstrip('/')
            except Exception:
                domain = ''

            availability = (
                'https://schema.org/InStock'
                if self._is_in_stock()
                else 'https://schema.org/OutOfStock'
            )

            image_path = '/web/image/product.template/%s/image_1024' % self.id
            image_url = '%s%s' % (domain, image_path) if domain else image_path

            slug = self.seo_name or self.id
            product_url = '%s/shop/%s' % (domain, slug) if domain else '/shop/%s' % slug

            description = (
                self.description_sale
                or _strip_html(self.description_ecommerce)
                or self.name
                or ''
            )

            valid_until = (date.today() + timedelta(days=30)).isoformat()

            data = {
                '@context': 'https://schema.org/',
                '@type': 'Product',
                'name': self.name or '',
                'description': description,
                'image': image_url,
                'url': product_url,
                'sku': self.default_code or '',
                'brand': {
                    '@type': 'Brand',
                    'name': self.feed_brand_id.name if getattr(self, 'feed_brand_id', False) and self.feed_brand_id else website_name,
                },
                'offers': {
                    '@type': 'Offer',
                    'url': product_url,
                    'priceCurrency': 'AUD',
                    'price': '%.2f' % (self.list_price or 0),
                    'priceValidUntil': valid_until,
                    'availability': availability,
                    'seller': {
                        '@type': 'Organization',
                        'name': website_name or '',
                    }
                }
            }
            return Markup(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            _logger.error('Schema JSON-LD error for product %s (id=%s): %s', self.name, self.id, e)
            return Markup('{}')
