# Copyright © 2022 Garazd Creation (<https://garazd.biz>)
# @author: Yurii Razumovskyi (<support@garazd.biz>)
# @author: Iryna Razumovska (<support@garazd.biz>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    feed_gtin = fields.Char(
        string='GTIN',
        compute='_compute_feed_gtin',
        inverse='_inverse_feed_gtin',
        store=True,
    )
    feed_mpn = fields.Char(
        string='MPN',
        compute='_compute_feed_mpn',
        inverse='_inverse_feed_mpn',
        store=True,
    )
    feed_isbn = fields.Char(
        string='ISBN',
        compute='_compute_feed_isbn',
        inverse='_inverse_feed_isbn',
        store=True,
    )

    @api.depends('product_variant_ids.feed_gtin')
    def _compute_feed_gtin(self):
        self._compute_template_field_from_variant_field('feed_gtin')

    def _inverse_feed_gtin(self):
        self._set_product_variant_field('feed_gtin')

    @api.depends('product_variant_ids.feed_mpn')
    def _compute_feed_mpn(self):
        self._compute_template_field_from_variant_field('feed_mpn')

    def _inverse_feed_mpn(self):
        self._set_product_variant_field('feed_mpn')

    @api.depends('product_variant_ids.feed_isbn')
    def _compute_feed_isbn(self):
        self._compute_template_field_from_variant_field('feed_isbn')

    def _inverse_feed_isbn(self):
        self._set_product_variant_field('feed_isbn')
