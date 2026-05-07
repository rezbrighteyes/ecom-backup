# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    credit_control = fields.Boolean(related="company_id.credit_control", readonly=False)

    overdue_control = fields.Boolean(
        related="company_id.overdue_control", readonly=False
    )
