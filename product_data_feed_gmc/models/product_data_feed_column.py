# Copyright © 2022 Garazd Creation (<https://garazd.biz>)
# @author: Yurii Razumovskyi (<support@garazd.biz>)
# @author: Iryna Razumovska (<support@garazd.biz>)
# License OPL-1 (https://www.odoo.com/documentation/14.0/legal/licenses.html).

from odoo import models


class ProductDataFeedColumn(models.Model):
    _inherit = "product.data.feed.column"

    def get_special_value(self, product):
        value = super(ProductDataFeedColumn, self).get_special_value(product)
        if self.recipient_id != self.env.ref('product_data_feed_gmc.recipient_google_merchant_center'):
            return value

        if self.special_type == 'price' and self.name == 'cost_of_goods_sold':
            value = self._get_price_value(product, price_field='standard_price')

        elif self.special_type == 'availability' \
                and self.feed_id.out_of_stock_mode == 'order'\
                and product.feed_gmc_availability \
                and value == self.feed_id.recipient_id.special_avail_order:
            # Replace order availability type to the specified value in a product
            # Tip from https://support.google.com/merchants/answer/6324448
            value = product.feed_gmc_availability

        elif self.special_type == 'product_attribute_multi':
            if self.multi_value_type != 'string':
                value = []
                for av in self._get_product_variant(product).product_template_attribute_value_ids:
                    value.append({
                        self.multi_dict_key: av.attribute_line_id.attribute_id.name,
                        self.multi_dict_value: av.name,
                    })

        return value
