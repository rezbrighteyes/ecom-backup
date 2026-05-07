# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    credit_control = fields.Boolean(
        string="Credit Limit Block",
        help="Blocking customer due to credit limit",
    )

    overdue_control = fields.Boolean(
        string="Overdue Invoice Block",
        help="Blocking customer due to overdue invoices",
    )
