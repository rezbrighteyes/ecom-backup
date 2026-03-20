# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo.exceptions import UserError, ValidationError
from odoo import api, fields, models, _


class ChooseDeliveryCarrier(models.TransientModel):
    _inherit = "choose.delivery.carrier"

    starshipit_rates_ids = fields.One2many(comodel_name='starshipit.available.services', inverse_name='choose_delivery_id', string='starshipit Rates')


    def update_price(self):
        if self.carrier_id.delivery_type == 'starshipit':
            response = self.carrier_id.starshipit_get_shipping_price(order=self.order_id)
            rate_list = [
                {
                    "service_name": rate.get("service_name"),
                    "service_code": rate.get("service_code"),
                    "service_price": rate.get("total_price"),
                    "choose_delivery_id": self.id, 
                }
                for rate in response
            ]

            self.env['starshipit.available.services'].search([]).unlink()

            self.env['starshipit.available.services'].create(rate_list)

            return super(ChooseDeliveryCarrier, self).update_price()

        else:
            return super(ChooseDeliveryCarrier, self).update_price()
