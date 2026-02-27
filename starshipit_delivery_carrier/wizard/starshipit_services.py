# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import models, fields,api


class SelectService(models.TransientModel):
    _name = "starshipit.available.services"

    
    service_name = fields.Char(string = 'Service Name')
    service_code = fields.Char(string = 'Service Code')
    service_price = fields.Float(string = 'Price')
    choose_delivery_id = fields.Many2one(comodel_name='choose.delivery.carrier', string='Choose Delivery Carrier ID')
    
    def add_selected_starshipit_rate(self):
        if self.choose_delivery_id:
            order = self.choose_delivery_id.order_id
            order.starshipit_service_price = self.service_price
            price = self.choose_delivery_id.carrier_id.starshipit_rate_shipment(order)
            self.choose_delivery_id.display_price = price['price']
            self.choose_delivery_id.delivery_price = price['price']
            order.starshipit_service_name = self.service_name
            order.starshipit_service_code = self.service_code
            picking = order.picking_ids
            picking.starshipit_service_price = self.service_price
            picking.starshipit_service_name = self.service_name
            picking.starshipit_service_code = self.service_code
            return {
                'name': 'Add a shipping method',
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'choose.delivery.carrier',
                'res_id': self.choose_delivery_id.id,
                'target': 'new',
            }
        else:
            active_id = self.env.context.get('active_id')
            picking_id = self.env['stock.picking'].search([('id', '=', int(active_id))])
            order = picking_id.sale_id
            order.starshipit_service_price = self.service_price
            order.starshipit_service_name = self.service_name
            order.starshipit_service_code = self.service_code
            picking_id.starshipit_service_price = self.service_price
            picking_id.starshipit_service_name = self.service_name
            picking_id.starshipit_service_code = self.service_code
            
            
            
            
            
