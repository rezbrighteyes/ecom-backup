from odoo import fields, models


class ProductDataFeedType(models.Model):
    _name = "product.data.feed.type"
    _description = 'Types of Product Data Feeds'

    name = fields.Char(required=True)
    recipient_id = fields.Many2one(
        comodel_name='product.data.feed.recipient',
        string='Recipient',
        ondelete='cascade',
        required=True,
    )

    _product_data_feed_type_recipient_uniq = models.Constraint(
        'UNIQUE (name, recipient_id)',
        "Data feed type must be unique per recipient.",
    )
