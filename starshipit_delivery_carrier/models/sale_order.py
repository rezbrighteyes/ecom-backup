# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import api, fields, models, _


class StarshipitSaleOrder(models.Model):
    _inherit = "sale.order"

    starshipit_service_name = fields.Char(string="Service Name")
    starshipit_service_code = fields.Char(string="Service Code")
    starshipit_service_price = fields.Float(string="Price")

    def _prepare_delivery_line_vals(self, carrier, price_unit):
        res = super()._prepare_delivery_line_vals(carrier, price_unit)
        if carrier.delivery_type == "starshipit":
            res["name"] = self.starshipit_service_name or res["name"]
        return res
