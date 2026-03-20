# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import api, fields, models, _

class StarshipitStockMove(models.Model):
    _inherit = "stock.move"

    def _get_new_picking_values(self):
        vals = super(StarshipitStockMove, self)._get_new_picking_values()
        order = self.group_id.sale_id
        if order and order.starshipit_service_price:
            vals.update({
                'starshipit_service_name' : order.starshipit_service_name,
                'starshipit_service_code' : order.starshipit_service_code,
                'starshipit_service_price' : order.starshipit_service_price
            })
        return vals
