# Copyright © 2022 Garazd Creation (<https://garazd.biz>)
# @author: Yurii Razumovskyi (<support@garazd.biz>)
# @author: Iryna Razumovska (<support@garazd.biz>)
# License OPL-1 (https://www.odoo.com/documentation/15.0/legal/licenses.html).

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    feed_gmc_availability = fields.Selection(
        string='Order Availability Type',
        selection=[
            ('backorder', 'BackOrder'),
            ('preorder', 'Pre-Order'),
        ],
        default='backorder',
        help='Availability type for products that are not in stock.',
    )
