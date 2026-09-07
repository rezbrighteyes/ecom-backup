"""Expose the per-website stockist settings in Website > Settings.

related=website_id.* is the Odoo pattern for per-website configuration: the
settings form already scopes itself to one website, so each brand's wording is
stored on its own website record rather than in a shared system parameter.
"""
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    stockist_cta_enabled = fields.Boolean(
        related="website_id.stockist_cta_enabled", readonly=False)
    stockist_cta_label = fields.Char(
        related="website_id.stockist_cta_label", readonly=False)
    stockist_cta_intro = fields.Text(
        related="website_id.stockist_cta_intro", readonly=False)
    stockist_helpdesk_team_id = fields.Many2one(
        related="website_id.stockist_helpdesk_team_id", readonly=False)
