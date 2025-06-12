# Copyright © 2024 Garazd Creation (https://garazd.biz)
# @author: Yurii Razumovskyi (support@garazd.biz)
# @author: Iryna Razumovska (support@garazd.biz)
# License OPL-1 (https://www.odoo.com/documentation/16.0/legal/licenses.html).

from odoo import _, api, fields, models
from .product_product import FEED_STOCK_AVAILABILITY


class ProductTemplate(models.Model):
    _inherit = "product.template"

    feed_force_availability = fields.Selection(
        selection=FEED_STOCK_AVAILABILITY,
        string='Forced Availability',
        compute='_compute_feed_force_availability',
        inverse='_inverse_feed_force_availability',
        help='If you need to set a forced status for the current product availability in data feeds, '
             'specify this field value.',
        tracking=True,
        store=True,
    )

    @api.depends('product_variant_ids', 'product_variant_ids.feed_force_availability')
    def _compute_feed_force_availability(self):
        self._compute_template_field_from_variant_field('feed_force_availability')

    def _inverse_feed_force_availability(self):
        self._set_product_variant_field('feed_force_availability')

    def _feed_get_attribute_value(self, attribute) -> str:
        """ Return the first value name for the specified attribute. """
        self.ensure_one()
        attribute_line = self.attribute_line_ids.filtered(lambda al: al.attribute_id == attribute)
        return attribute_line.value_ids[:1].name if attribute_line.value_ids else ''

    def action_feed_open_variants(self):
        self.ensure_one()
        return {
            'name': _('Product Variants'),
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'res_id': self.product_variant_ids[0].id if len(self.product_variant_ids) == 1 else False,
            'view_mode': 'form' if len(self.product_variant_ids) == 1 else 'list,form',
            'domain': [('id', 'in', self.product_variant_ids.ids)],
        }
