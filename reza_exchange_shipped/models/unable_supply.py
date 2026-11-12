# -*- coding: utf-8 -*-
from odoo import fields, models


class RezaUnableSupplyWizard(models.TransientModel):
    _inherit = "reza.unable.supply.wizard"

    reza_edbert_handled = fields.Boolean(
        help="Set by Exchange (shipped). The goods went back into stock through a "
        "customer return and are sent back to Edbert by reza.edbert.return, so the "
        "\"Edbert purchase already raised\" refusal does not apply.")

    def _check_edbert_purchase(self, order):
        if self.reza_edbert_handled:
            return
        return super()._check_edbert_purchase(order)
