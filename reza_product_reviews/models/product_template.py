# -- coding: utf-8 --
from odoo import api, fields, models
from odoo.fields import Domain


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

    def _rating_domain(self):
        """Only approved reviews count, in rating_count / rating_avg and in the
        portal chatter's rating_stats (rating_get_stats -> _rating_get_repartition).
        On 18 the portal_message_fetch override recomputed those stats; that
        route is gone in 20 and every stats path goes through this domain."""
        return super()._rating_domain() & Domain('is_approved', '=', True)

    @api.depends('rating_ids', 'rating_ids.rating', 'rating_ids.consumed', 'rating_ids.is_approved')
    def _compute_rating_stats(self):
        """Override to only count approved reviews."""
        domain = self._rating_domain() & Domain('rating', '>=', 1)
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

    def _get_share_message_domain(self):
        """Hide messages carrying an unapproved review from the portal chatter
        (/mail/chatter_fetch in 20 filters with this domain). Replaces the 18
        portal_message_fetch override, which no longer exists."""
        return super()._get_share_message_domain() & Domain(
            'rating_ids', 'not any', [('is_approved', '=', False)]
        )
