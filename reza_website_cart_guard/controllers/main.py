from odoo.http import request, route
from odoo.addons.website_sale.controllers.cart import Cart

from ..models.website import GUARD_PRODUCT_ATTR


class RezaWebsiteSaleCartGuard(Cart):
    """Tell website._create_cart() which product a new cart is created for,
    so the per-product hourly limit applies. The guard itself runs in
    website._create_cart(), which Odoo 20 calls only when the visitor has no
    draft cart yet (quick_add calls add_to_cart, so it is covered too)."""

    @route()
    def add_to_cart(self, product_template_id, product_id, quantity, *args, **kwargs):
        setattr(request, GUARD_PRODUCT_ATTR, product_id)
        return super().add_to_cart(product_template_id, product_id, quantity, *args, **kwargs)
