# -- coding: utf-8 --
from odoo import api, models

# Production partners of Luke, April and Reza.
REVIEW_CHANNEL_PARTNER_IDS = [10, 11, 13730]


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    @api.model
    def _reza_review_channel_add_members(self):
        """Called once at install. The 18 data file created the members with
        hard-coded partner ids, which raises a foreign-key error on any
        database where those partners do not exist; add only the ones that do."""
        channel = self.env.ref('reza_product_reviews.channel_product_reviews', raise_if_not_found=False)
        partners = self.env['res.partner'].browse(REVIEW_CHANNEL_PARTNER_IDS).exists()
        if channel and partners:
            channel._add_members(partners=partners)
