# -- coding: utf-8 --
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    review_count = fields.Integer(
        string='Reviews',
        compute='_compute_review_count',
    )

    def _compute_review_count(self):
        for product in self:
            product.review_count = self.env['rating.rating'].sudo().search_count([
                ('res_model', '=', 'product.template'),
                ('res_id', '=', product.id),
            ])

    def action_open_reviews(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reviews',
            'res_model': 'rating.rating',
            'view_mode': 'list,form',
            'domain': [
                ('res_model', '=', 'product.template'),
                ('res_id', '=', self.id),
            ],
        }