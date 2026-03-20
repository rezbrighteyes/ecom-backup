# -*- coding: utf-8 -*-
#################################################################################
##    Copyright (c) 2025-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import models, fields, api

class SOWarningWizard(models.TransientModel):
    _name = 'so.warning.wizard'
    _description = "Sale order package assign in stock.picking warning Wizard"

    picking_id = fields.Many2one('stock.picking', string='Picking')

    def action_confirm(self):
        if self.picking_id:
            self.picking_id.pack_order_stock_picking(self.picking_id)