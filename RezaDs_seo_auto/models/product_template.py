# -- coding: utf-8 --
# Copyright 2026 Reza Shiraz
# License LGPL-3.

import re
import json
import logging
import unicodedata
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


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._set_seo_defaults()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ('name', 'description_ecommerce', 'feed_brand_id', 'tag_ids')):
            self._set_seo_defaults(
                name_changed='name' in vals,
                desc_changed='description_ecommerce' in vals,
            )
        return res

    def _set_seo_defaults(self, name_changed=False, desc_changed=False):
        for record in self:
            updates = {}

            if not record.website_meta_title or name_changed:
                updates['website_meta_title'] = record.name[:60]

            if not record.seo_name or name_changed:
                updates['seo_name'] = _make_slug(record.name)

            if not record.website_meta_description or desc_changed:
                desc = _extract_seo_description(record.description_ecommerce)
                if desc:
                    updates['website_meta_description'] = desc

            if not record.website_meta_keywords or name_changed:
                keywords = []
                if getattr(record, 'feed_brand_id', False):
                    keywords.append(record.feed_brand_id.name)
                if record.categ_id:
                    keywords.append(record.categ_id.name)
                if getattr(record, 'tag_ids', False):
                    keywords += record.tag_ids.mapped('name')
                keywords.append(record.name)
                updates['website_meta_keywords'] = ', '.join(keywords)

            if updates:
                super(ProductTemplate, record).write(updates)

    def get_schema_jsonld(self, website_name=''):
        self.ensure_one()
        try:
            availability = (
                'https://schema.org/InStock'
                if self.sudo().qty_available > 0
                else 'https://schema.org/OutOfStock'
            )
            data = {
                '@context': 'https://schema.org/',
                '@type': 'Product',
                'name': self.name or '',
                'description': self.description_sale or self.name or '',
                'sku': self.default_code or '',
                'brand': {
                    '@type': 'Brand',
                    'name': self.feed_brand_id.name if getattr(self, 'feed_brand_id', False) and self.feed_brand_id else website_name,
                },
                'offers': {
                    '@type': 'Offer',
                    'priceCurrency': 'AUD',
                    'price': '%.2f' % (self.list_price or 0),
                    'availability': availability,
                    'seller': {
                        '@type': 'Organization',
                        'name': website_name or '',
                    }
                }
            }
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            _logger.error('Schema JSON-LD error for product %s (id=%s): %s', self.name, self.id, e)
            return '{}'
