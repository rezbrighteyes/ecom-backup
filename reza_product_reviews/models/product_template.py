# -- coding: utf-8 --
from odoo import api, fields, models
from odoo.osv import expression


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

    @api.depends('rating_ids', 'rating_ids.rating', 'rating_ids.consumed', 'rating_ids.is_approved')
    def _compute_rating_stats(self):
        """Override to only count approved reviews."""
        domain = expression.AND([
            self._rating_domain(),
            [('rating', '>=', 1), ('is_approved', '=', True)],
        ])
        read_group_res = self.env['rating.rating']._read_group(
            domain, ['res_id'], aggregates=['__count', 'rating:avg']
        )
        mapping = {
            res_id: {'rating_count': count, 'rating_avg': rating_avg}
            for res_id, count, rating_avg in read_group_res
        }
        for record in self:
            record.rating_count = mapping.get(record.id, {}).get('rating_count', 0)
            record.rating_avg = mapping.get(record.id, {}).get('rating_avg', 0)