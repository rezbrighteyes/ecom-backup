import hashlib
import logging

from werkzeug.exceptions import TooManyRequests

from odoo.http import request, route
from odoo.addons.website_sale.controllers.main import WebsiteSale


_logger = logging.getLogger(__name__)


class RezaWebsiteSaleCartGuard(WebsiteSale):

    def _reza_cart_guard_int_param(self, name, default):
        value = request.env["ir.config_parameter"].sudo().get_param(name, str(default))
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return default

    def _reza_cart_guard_enabled(self):
        value = request.env["ir.config_parameter"].sudo().get_param(
            "reza_cart_guard.enabled", "True"
        )
        return str(value).strip().lower() not in {"0", "false", "no", "off"}

    def _reza_cart_guard_ip_hash(self):
        # Odoo.sh runs Odoo in proxy mode, so remote_addr is the proxy-validated
        # client address. Only fall back to X-Forwarded-For for other deployments.
        forwarded = request.httprequest.headers.get("X-Forwarded-For", "")
        ip = request.httprequest.remote_addr or forwarded.split(",")[0].strip() or ""
        secret = request.env["ir.config_parameter"].sudo().get_param(
            "database.secret", "reza-cart-guard"
        )
        return hashlib.sha256(f"{secret}:{ip}".encode()).hexdigest()

    def _reza_check_anonymous_cart_creation(self, product_id):
        if not self._reza_cart_guard_enabled() or not request.env.user._is_public():
            return

        # Existing carts do not create another quotation, so their normal updates
        # should not consume the anonymous cart-creation allowance.
        existing_order = request.website.sale_get_order()
        if existing_order and existing_order.state == "draft":
            return

        ip_hash = self._reza_cart_guard_ip_hash()
        hour_limit = self._reza_cart_guard_int_param("reza_cart_guard.hour_limit", 6)
        day_limit = self._reza_cart_guard_int_param("reza_cart_guard.day_limit", 20)
        product_hour_limit = self._reza_cart_guard_int_param(
            "reza_cart_guard.product_hour_limit", 3
        )
        allowed = request.env["reza.website.cart.attempt"].sudo().check_and_record(
            website_id=request.website.id,
            ip_hash=ip_hash,
            product_id=int(product_id),
            hour_limit=hour_limit,
            day_limit=day_limit,
            product_hour_limit=product_hour_limit,
        )
        if allowed:
            return

        _logger.warning(
            "Blocked anonymous cart creation: website=%s ip_hash=%s product_id=%s",
            request.website.id,
            ip_hash[:12],
            product_id,
        )
        raise TooManyRequests(
            description="Too many new shopping carts were created. Please try again later."
        )

    @route()
    def cart_update(
        self,
        product_id,
        add_qty=1,
        set_qty=0,
        product_custom_attribute_values=None,
        no_variant_attribute_value_ids=None,
        **kwargs,
    ):
        self._reza_check_anonymous_cart_creation(product_id)
        return super().cart_update(
            product_id=product_id,
            add_qty=add_qty,
            set_qty=set_qty,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            **kwargs,
        )

    @route()
    def cart_update_json(
        self,
        product_id,
        line_id=None,
        add_qty=None,
        set_qty=None,
        display=True,
        product_custom_attribute_values=None,
        no_variant_attribute_value_ids=None,
        **kwargs,
    ):
        self._reza_check_anonymous_cart_creation(product_id)
        return super().cart_update_json(
            product_id=product_id,
            line_id=line_id,
            add_qty=add_qty,
            set_qty=set_qty,
            display=display,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            **kwargs,
        )
