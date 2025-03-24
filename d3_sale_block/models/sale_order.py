# -*- coding: utf-8 -*-

from odoo import _, fields, models

from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    bypass_credit = fields.Boolean(
        string="Bypass Credit?", default=False, copy=False, tracking=True
    )

    def action_confirm(self):
        for order in self.filtered("partner_credit_warning"):
            if order.shopify_order_id:
                continue
            if order.website_id:
                act_type_xmlid = "mail.mail_activity_data_todo"
                date_deadline = fields.Date.today()
                summary = "Over Credit"
                note = "This customer has over credit and confirmed the order using a payment method."
                user_id = order.partner_id.user_id and order.partner_id.user_id.id
                order.activity_schedule(
                    act_type_xmlid=act_type_xmlid,
                    date_deadline=date_deadline,
                    summary=summary,
                    note=note,
                    user_id=user_id,
                )
                continue
            if not order.bypass_credit:
                raise UserError(
                    _("Unable to confirm order while customer is over credit")
                )
        return super(SaleOrder, self).action_confirm()
