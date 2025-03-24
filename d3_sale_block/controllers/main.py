import re
import markupsafe

from odoo import fields, http
from odoo.http import request
from odoo.addons.payment.controllers import portal as payment_portal


class WebsiteSale(payment_portal.PaymentPortal):

    @http.route(['/order/check_credit_limit'], type='json', auth="public", methods=['POST'], website=True, csrf=False)
    def check_credit_limit(self, **kw):
        order = request.website.sale_get_order(force_create=True)
        values = {}
        if order.partner_credit_warning:
            formatted_credit_message = re.sub(r'(\r\n|\r|\n)', '<br/>', order.partner_credit_warning)
            formatted_credit_message = markupsafe.Markup(formatted_credit_message)
            values['sale_credit_limit_alert_template'] = request.env['ir.ui.view']._render_template(
                "d3_sale_block.sale_credit_limit_alert_template", {
                    'credit_limit_alert': formatted_credit_message,
                }
            )
        return values