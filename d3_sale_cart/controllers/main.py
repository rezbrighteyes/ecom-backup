# -*- coding: utf-8 -*-

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class D3SaleCartRecovery(http.Controller):

    @http.route(
        "/d3_sale_cart/recover/<int:order_id>/<string:access_token>/<string:coupon_code>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def recover_cart_with_coupon(self, order_id, access_token, coupon_code, **kwargs):
        order = request.env["sale.order"].sudo().browse(order_id).exists()
        if not order or order.access_token != access_token:
            raise NotFound()
        if order.state != "draft":
            return request.redirect(order.get_portal_url())

        request.session["sale_order_id"] = order.id
        request.session["pending_coupon_code"] = coupon_code.strip()
        return request.redirect("/shop/cart")
