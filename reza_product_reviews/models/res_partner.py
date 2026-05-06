# -- coding: utf-8 --
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    review_count = fields.Integer(
        string='Reviews',
        compute='_compute_review_count',
    )

    def _compute_review_count(self):
        for partner in self:
            partner.review_count = self.env['rating.rating'].sudo().search_count([
                ('partner_id', '=', partner.id),
                ('res_model', '=', 'product.template'),
            ])

    def action_open_reviews(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reviews',
            'res_model': 'rating.rating',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.id),
                ('res_model', '=', 'product.template'),
            ],
        }