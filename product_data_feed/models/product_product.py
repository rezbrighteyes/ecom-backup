# Copyright © 2024 Garazd Creation (https://garazd.biz)
# @author: Yurii Razumovskyi (support@garazd.biz)
# @author: Iryna Razumovska (support@garazd.biz)
# License OPL-1 (https://www.odoo.com/documentation/16.0/legal/licenses.html).

from odoo import _, fields, models

FEED_STOCK_AVAILABILITY = [('in_stock', 'In Stock'), ('out_of_stock', 'Out Of Stock')]


class ProductProduct(models.Model):
    _inherit = "product.product"

    feed_force_availability = fields.Selection(
        selection=FEED_STOCK_AVAILABILITY,
        string='Forced Availability',
        help='If you need to set a forced status for the current product availability, specify this field value.',
        tracking=True,
    )

    def action_feed_open_template(self):
        self.ensure_one()
        return {
            'name': self.product_tmpl_id.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'res_id': self.product_tmpl_id.id,
            'view_mode': 'form',
        }
