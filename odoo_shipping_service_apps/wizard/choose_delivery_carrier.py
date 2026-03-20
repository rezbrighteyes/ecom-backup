from odoo import models

class ChooseDeliveryCarrier(models.TransientModel):
    _inherit = 'choose.delivery.carrier'

    def update_price(self):
        for wizard in self:
            if wizard.order_id and wizard.carrier_id:
                wizard.order_id.write({
                    'carrier_id': wizard.carrier_id.id,
                    'recompute_delivery_price': False,
                    'delivery_message': wizard.delivery_message,
                })

                wizard.order_id.set_delivery_line(wizard.carrier_id, wizard.delivery_price)

        return super(ChooseDeliveryCarrier, self).update_price()
