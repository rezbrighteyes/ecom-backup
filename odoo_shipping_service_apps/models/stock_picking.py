# -*- coding: utf-8 -*-
#################################################################################
# Copyright (c) 2025-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare
import logging
_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def get_picking_price(self, package_id):
        move_line_ids = self.env['stock.move.line'].search(
            [('result_package_id', '=', package_id.id)])
        return sum([x.quantity * x.product_id.list_price for x in move_line_ids])

    @api.model
    def wk_update_package(self, package_id=None):
        if self.carrier_id.delivery_type not in ['base_on_rule', 'fixed']:
            packaging_id = package_id.packaging_id
            if package_id and (not packaging_id):
                packaging_id = self.carrier_id.packaging_type_id
                package_id.packaging_id = packaging_id.id
            amount = self.get_picking_price(package_id)
            package_id.cover_amount = packaging_id.get_cover_amount(amount)
        return True
    

    def _get_cover_amount_without_qty_done(self):
        picking_move_lines = self.move_line_ids
        move_line_ids = picking_move_lines.filtered(lambda ml: 
            float_compare(ml.quantity, 0.0, precision_rounding=ml.product_uom_id.rounding) > 0 and not ml.result_package_id)

        if not move_line_ids:
            move_line_ids = picking_move_lines.filtered(lambda ml: 
                        float_compare(ml.quantity_product_uom, 0.0, precision_rounding=ml.product_uom_id.rounding) > 0 and 
                        float_compare(ml.quantity, 0.0, precision_rounding=ml.product_uom_id.rounding) == 0)
        price = 0
        if move_line_ids:
            for line in move_line_ids:
                if line.quantity:
                    qty = line.quantity
                else:
                    qty = line.quantity_product_uom
                    
                if line.move_id.sale_line_id:
                    price_unit = line.move_id.sale_line_id.price_unit*qty or 0.0
                else:
                    price_unit = line.product_id.lst_price*qty or 0.0
                price += price_unit

        total_weight = sum([po.quantity * po.product_id.weight for po in move_line_ids]) 

        if not total_weight:
            total_weight = sum([po.quantity_product_uom * po.product_id.weight for po in move_line_ids]) 
        return price, total_weight

    def action_put_in_pack(self):
        self.ensure_one()
        cover = 0
        carrier_id = self.carrier_id
        move_line_ids = [
            po for po in self.move_line_ids if po.quantity > 0 and not po.result_package_id]
        total_weight = sum(
            [po.quantity * po.product_id.weight for po in move_line_ids])

        if carrier_id.packaging_type_id.cover_amount_option == 'fixed':
            cover = self.carrier_id.packaging_type_id.cover_amount
        else:
            cover_amount = sum(
                [po.quantity * po.product_id.lst_price for po in move_line_ids])
            cover = cover_amount

        if total_weight == 0:
            shipping_weight = self.carrier_id.default_product_weight
        else:
            shipping_weight = total_weight

        if not move_line_ids:
            cover, shipping_weight = self._get_cover_amount_without_qty_done()

        res = super(StockPicking, self).action_put_in_pack()
        if isinstance(res, dict):
            default_move_line_ids = res.get('context', {}).get('default_move_line_ids')
        else:
            default_move_line_ids = res.move_line_ids.ids
        # default_move_line_ids = res.move_line_ids if res.move_line_ids else res.get('context', {}) and res.get('context', {}).get('default_move_line_ids') or False
        if res and (type(res) == dict):
            context = res.get('context') and res.get(
                'context').copy() or dict()
            delivery_type = context.get('current_package_carrier_type')
            ctx = {
                'no_description':
                not(delivery_type in ['fedex', 'dhl',
                    'ups', 'auspost', 'canada_post', 'my_dhl','freightview']),
                'no_cover_amount':
                    not(delivery_type in [
                        'fedex', 'dhl', 'ups', 'usps', 'auspost', 'canada_post','my_dhl','freightview']),
                'no_edt_document':
                    not(delivery_type in ['fedex', 'ups']),
                'current_package_picking_id': self.id,

            }

            if carrier_id and carrier_id.delivery_type not in ['base_on_rule', 'fixed']:
                ctx['default_delivery_packaging_id'] = self.carrier_id.packaging_type_id.id
                ctx['default_height'] = self.carrier_id.packaging_type_id.height
                ctx['default_width'] = self.carrier_id.packaging_type_id.width
                ctx['default_length'] = self.carrier_id.packaging_type_id.packaging_length
                ctx['default_cover_amount'] = cover
                ctx['default_shipping_weight'] = shipping_weight
            context.update(ctx)
            res['context'].update(context)

            """
            Extra code for creating with default values beacuse now wizard is not created with default values
            """
            """
            If any error came in package or picking please check the feilds of wizard and add the remaining feilds with value if any
            """
            vals = dict(
                package_type_id=self.carrier_id.packaging_type_id.id,
                height=self.carrier_id.packaging_type_id.height,
                width=self.carrier_id.packaging_type_id.width,
                wkk_length=self.carrier_id.packaging_type_id.packaging_length,
                cover_amount=cover,
                shipping_weight=shipping_weight,
                move_line_ids=default_move_line_ids,
                package_carrier_type=self.carrier_id.delivery_type,
                # picking_id=res['context']['current_package_picking_id'], # TODO field is does not exists 
            )
            wiz = self.env['stock.put.in.pack'].sudo().create(vals)
            wiz.onchange_delivery_packaging_id()
            res['res_id'] = wiz.id
        return res

    @api.depends('move_line_ids', 'move_line_ids.result_package_id')
    def _compute_cover_amount(self):
        for obj in self:
            obj.cover_amount = sum(obj.move_line_ids.result_package_id.mapped('cover_amount'))

    label_genrated = fields.Boolean(string='Label Generated', copy=False)
    order_pack_button = fields.Boolean(help='Show or not',compute='order_pck_button')
    shipment_uom_id = fields.Many2one(related='carrier_id.uom_id', readonly=True,
                                      help="Unit of measurement for use by Delivery method", copy=False)

    date_delivery = fields.Date(string='Expected Date Of Delivery',
                                help='Expected Date Of Delivery :The delivery time stamp provided by Shipment Service', copy=False, readonly=True)
    weight_shipment = fields.Float(
        string='Send Weight', copy=False, readonly=True)
    cover_amount = fields.Float(
        string='Cover Amount',
        compute='_compute_cover_amount',
        copy=False, readonly=True)

    def action_cancel(self):
        avilable_carriers_list = self.get_all_wk_carriers()
        for obj in self:
            if obj.carrier_id.delivery_type and (obj.carrier_id.delivery_type not in ['base_on_rule', 'fixed']) and (obj.carrier_id.delivery_type in avilable_carriers_list):
                if obj.label_genrated == True:
                    raise ValidationError(
                        'Please cancel the shipment before canceling  picking! ')
        return super(StockPicking, self).action_cancel()
            

    def do_new_transfer(self):
        for pick in self:
            carrier_id = pick.carrier_id
            if carrier_id and (carrier_id.delivery_type not in ['base_on_rule', 'fixed']):
                if not len(pick.move_line_ids.result_package_id):
                    raise ValidationError(
                        'Create the package first for picking %s before sending to shipper.' % (pick.name))
        return super(StockPicking, self).do_new_transfer()

    def get_all_wk_carriers(self):
        """
        Created to add and detect Webkul avaialable delivery carriers 
        """
        available_carriers = []
        return available_carriers
    
    def send_to_shipper(self):
        self.ensure_one()
        avilable_carriers_list = self.get_all_wk_carriers()
        if self.carrier_id.delivery_type and (self.carrier_id.delivery_type not in ['base_on_rule', 'fixed']) and (self.carrier_id.delivery_type in avilable_carriers_list):
            if not len(self.move_line_ids.result_package_id):
                raise ValidationError(
                    'Create the package first for picking %s before sending to shipper.' % (self.name))
            else:
                # try:
                res = self.carrier_id.send_shipping(self)
                self.carrier_price = res.get('exact_price')
                self.carrier_tracking_ref = res.get(
                    'tracking_number') and res.get('tracking_number').strip(',')
                self.label_genrated = True
                self.date_delivery = res.get('date_delivery')
                self.weight_shipment = float(res.get('weight'))
                msg = _("Shipment sent to carrier %s for expedition with tracking number %s") % (
                    self.carrier_id.delivery_type, self.carrier_tracking_ref)
                self.message_post(
                    body=msg,
                    subject="Attachments of tracking",
                    attachments=res.get('attachments')
                )
                # except Exception as e:
                #     return self.carrier_id._shipping_genrated_message(e)
        else:
            return super(StockPicking, self).send_to_shipper()


    @api.model
    def unset_fields_prev(self):
        self.carrier_tracking_ref = False
        self.carrier_price = False
        self.label_genrated = False
        self.date_delivery = False
        self.weight_shipment = False
        # self.number_of_packages = False
        return True

    def cancel_shipment(self):
        self.ensure_one()
        # try:
        if self.carrier_id.void_shipment:
            self.carrier_id.cancel_shipment(self)
            msg = "Shipment of  %s  has been canceled" % self.carrier_tracking_ref
            self.message_post(body=msg)
            self.unset_fields_prev()
        else:
            msg = 'Void Shipment not allowed, please contact your Admin to enable the  Void Shipment for %s.' % (
                self.carrier_id.name)
            self.message_post(
                body=msg, subject="Not allowed to Void the Shipment.")
            return self.carrier_id._shipping_genrated_message(msg)
        # except Exception as e:
        #     return self.carrier_id._shipping_genrated_message(e)
    
    def order_pck_button(self):
        if self.sale_id.multi_package:
            if self.sale_id.create_package == 'auto' and self.sale_id.wk_packaging_ids:
                if self.sale_id.carrier_id.package_creation_type!='all_products':
                    missing_package = any(not line.pckage_id for line in self.sale_id.wk_packaging_ids)
                    self.order_pack_button = missing_package
                else:
                    missing_package = False if self.sale_id.package_id.id else True
                    self.order_pack_button = missing_package
            elif self.sale_id.create_package == 'manual' and self.sale_id.wk_manual_packaging_ids:
                missing_package = any(not line.package_id for line in self.sale_id.wk_manual_packaging_ids)
                self.order_pack_button = missing_package
            else:
                self.order_pack_button = True
        else:
            self.order_pack_button = True
                
    def pack_order_stock_picking(self,picking):
        sale = picking.sale_id
        if sale.multi_package:
                picking.move_line_ids.unlink()

                if sale.create_package == 'auto':
                    if self.sale_id.carrier_id.package_creation_type!='all_products':
                        packaging_lines = sale.wk_packaging_ids
                    else: 
                        for line in sale.order_line:
                            if not line.product_id or line.product_id.type == 'service':
                                continue   

                            self.env['stock.move.line'].create({
                                'picking_id': picking.id,
                                'product_id': line.product_id.id,
                                'product_uom_id': line.product_uom_id.id,
                                'quantity': line.product_uom_qty ,  
                                'location_id': picking.location_id.id,
                                'location_dest_id': picking.location_dest_id.id,
                                'result_package_id': sale.package_id.id,
                            })
                        return 1
                elif sale.create_package == 'manual':
                    packaging_lines = sale.wk_manual_packaging_ids
                else:
                    packaging_lines = []
                for line in packaging_lines:
                    package_id = line.pckage_id if sale.create_package == 'auto' else line.package_id
                    if not line.product_id or not package_id:
                        continue

                    self.env['stock.move.line'].create({
                        'picking_id': picking.id,
                        'product_id': line.product_id.id,
                        'product_uom_id': line.product_id.uom_id.id,
                        'quantity': line.quantity , 
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'result_package_id': package_id.id,
                    })
    def order_pack(self):
        for picking in self:
            if picking.move_line_ids.filtered(lambda m: m.result_package_id):
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Package Already Assigned',
                    'res_model': 'so.warning.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_picking_id': picking.id,
                    }
                }
            self.pack_order_stock_picking(picking)
