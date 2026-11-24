import hashlib
import logging

from werkzeug.exceptions import TooManyRequests

from odoo import models
from odoo.http import request


_logger = logging.getLogger(__name__)

# Odoo 20: every new website cart goes through website._create_cart()
# (/shop/cart/add, /shop/cart/quick_add, /my/orders/reorder, event and booth
# registration all call `request.cart or website._create_cart()`), and
# request.cart only holds a DRAFT cart of this website. So guarding
# _create_cart() limits NEW carts only; an existing cart never gets here.
GUARD_PRODUCT_ATTR = "reza_cart_guard_product_id"


class Website(models.Model):
    _inherit = "website"

    def _reza_cart_guard_int_param(self, name, default):
        value = self.env["ir.config_parameter"].sudo().get_int(name, default)
        return max(value, 1)

    def _reza_cart_guard_enabled(self):
        value = self.env["ir.config_parameter"].sudo().get_str(
            "reza_cart_guard.enabled", "True"
        )
        return str(value).strip().lower() not in {"0", "false", "no", "off"}

    def _reza_cart_guard_ip_hash(self):
        # Odoo.sh runs Odoo in proxy mode, so remote_addr is the proxy-validated
        # client address. Only fall back to X-Forwarded-For for other deployments.
        forwarded = request.httprequest.headers.get("X-Forwarded-For", "")
        ip = request.httprequest.remote_addr or forwarded.split(",")[0].strip() or ""
        secret = self.env["ir.config_parameter"].sudo().get_str(
            "database.secret", "reza-cart-guard"
        )
        return hashlib.sha256(f"{secret}:{ip}".encode()).hexdigest()

    def _reza_check_anonymous_cart_creation(self):
        self.ensure_one()
        if not request or not self._reza_cart_guard_enabled() or not self.env.user._is_public():
            return

        product_id = getattr(request, GUARD_PRODUCT_ATTR, None)
        product_id = int(product_id) if product_id else False
        ip_hash = self._reza_cart_guard_ip_hash()
        hour_limit = self._reza_cart_guard_int_param("reza_cart_guard.hour_limit", 6)
        day_limit = self._reza_cart_guard_int_param("reza_cart_guard.day_limit", 20)
        product_hour_limit = self._reza_cart_guard_int_param(
            "reza_cart_guard.product_hour_limit", 3
        )
        allowed = self.env["reza.website.cart.attempt"].sudo().check_and_record(
            website_id=self.id,
            ip_hash=ip_hash,
            product_id=product_id,
            hour_limit=hour_limit,
            day_limit=day_limit,
            product_hour_limit=product_hour_limit,
        )
        if allowed:
            return

        _logger.warning(
            "Blocked anonymous cart creation: website=%s ip_hash=%s product_id=%s",
            self.id,
            ip_hash[:12],
            product_id,
        )
        raise TooManyRequests(
            description="Too many new shopping carts were created. Please try again later."
        )

    def _create_cart(self):
        self._reza_check_anonymous_cart_creation()
        return super()._create_cart()
