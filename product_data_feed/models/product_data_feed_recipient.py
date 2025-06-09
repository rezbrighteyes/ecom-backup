# Copyright © 2020 Garazd Creation (<https://garazd.biz>)
# @author: Yurii Razumovskyi (<support@garazd.biz>)
# @author: Iryna Razumovska (<support@garazd.biz>)
# License OPL-1 (https://www.odoo.com/documentation/14.0/legal/licenses.html).

from typing import Dict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductDataFeedRecipient(models.Model):
    _name = "product.data.feed.recipient"
    _description = 'Product Data Feed Recipients'

    name = fields.Char(required=True)
    # Product availability values
    special_avail_in = fields.Char(
        string='In Stock',
        default='in stock',
        help='Value that is used when products are in stock.',
    )
    special_avail_out = fields.Char(
        string='Out of Stock',
        default='out of stock',
        help='Value that is used when products are out of stock.',
    )
    special_avail_order = fields.Char(
        string='Can be order',
        default='available for order',
        help='Value that is used when products can be ordered.',
    )

    @api.constrains('name')
    def _check_name(self):
        for recipient in self:
            if self.search_count([('name', '=', recipient.name)]) > 1:
                raise ValidationError(_('The name of a recipient must be unique.'))

    def _get_availability_values(self) -> Dict:
        self.ensure_one()
        return {'in_stock': self.special_avail_in, 'out_of_stock': self.special_avail_out}
