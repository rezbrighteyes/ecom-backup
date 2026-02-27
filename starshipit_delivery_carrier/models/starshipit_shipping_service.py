# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import api, fields, models, _


class ShippingStarshipit(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(selection_add=[('starshipit', 'Starshipit')], ondelete={'starshipit': 'cascade'})
    starshipit_api_key = fields.Char(string="API Key")
    starshipit_subscription_key = fields.Char(string="Subscription Key")
    starshipit_service_name = fields.Char(string = 'Service Name')
    starshipit_service_code = fields.Char(string = 'Service Code')
    starshipit_service_price = fields.Float(string = 'Price')


class ProductPackage(models.Model):
    _inherit = 'product.package'

    delivery_type = fields.Selection(
        selection_add=[('starshipit', 'Starshipit')]
    )


class ProductPackaging(models.Model):
    _inherit = 'stock.package.type'

    package_carrier_type = fields.Selection(
        selection_add=[('starshipit', 'Starshipit')]
    )


    
class StockPicking(models.Model):
    _inherit = 'stock.picking'

    starshipit_service_name = fields.Char(string = 'Service Name')
    starshipit_service_code = fields.Char(string = 'Service Code')
    starshipit_service_price = fields.Float(string = 'Price')
    orders = fields.Char(string= 'Orders')


    def get_all_wk_carriers(self):
        res = super(StockPicking, self).get_all_wk_carriers()
        res.append('starshipit')
        return res
        
    def get_starshipit_rates(self):
        for picking in self:
            carrier = picking.carrier_id
            response = carrier.starshipit_get_shipping_price(picking=picking)
            rate_list = [
                {
                    "service_name": rate.get("service_name"),
                    "service_code": rate.get("service_code"),
                    "service_price": rate.get("total_price")
                }
                for rate in response
            ]
            
            self.env['starshipit.available.services'].search([]).unlink()
            self.env['starshipit.available.services'].create(rate_list)
            view = self.env.ref('starshipit_delivery_carrier.wizard_starshipit_services_list')
            return {
                'name': _('Select starshipit Rate'),
                'type': 'ir.actions.act_window',
                'view_mode': 'list',
                'res_model': 'starshipit.available.services',
                'views': [(view.id, 'list')],
                'target': 'new',
            }


