# Copyright © 2020 Garazd Creation (<https://garazd.biz>)
# @author: Yurii Razumovskyi (<support@garazd.biz>)
# @author: Iryna Razumovska (<support@garazd.biz>)
# License OPL-1 (https://www.odoo.com/documentation/14.0/legal/licenses.html).

from odoo import api, fields, models


class ProductDataFeedColumnValue(models.Model):
    _name = "product.data.feed.column.value"
    _description = 'Product Data Feed Column Value'

    @api.model
    def _get_recipients(self):
        return self.env['product.data.feed']._get_recipients()

    name = fields.Char(
        string='Value',
        required=True,
    )
    recipient_id = fields.Many2one(
        comodel_name='product.data.feed.recipient',
        string='Recipient',
        required=True,
        ondelete='cascade',
    )
    column_name = fields.Char(required=True)
