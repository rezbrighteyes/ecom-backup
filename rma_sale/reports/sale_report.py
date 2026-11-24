# Copyright 2026 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.tools import SQL


class SaleReport(models.Model):
    _inherit = "sale.report"

    rma_count = fields.Integer(
        string="Number of RMAs",
        readonly=True,
    )

    # Odoo 20 builds sale.report from _select_dict/_groupby_list on a
    # TableSQL of sale.order.line (it replaced _select_additional_fields and
    # _group_by_sale).
    def _select_dict(self, table):
        return super()._select_dict(table) | {
            "rma_count": SQL("COALESCE(%s, 0)", table.rma_count),
        }

    def _groupby_list(self, table):
        return super()._groupby_list(table) + [table.rma_count]
