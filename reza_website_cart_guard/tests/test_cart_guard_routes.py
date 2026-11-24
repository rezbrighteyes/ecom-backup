from odoo.tests import HttpCase, tagged
from odoo.tests.common import JsonRpcException


@tagged("post_install", "-at_install")
class TestCartGuardRoutes(HttpCase):
    """Anonymous /shop/cart/add over real HTTP: the guard limits NEW carts
    and never counts or blocks an update to an existing cart."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Guard Route Product",
            "list_price": 10.0,
            "sale_ok": True,
            "is_published": True,
            "website_id": False,
        })
        cls.other_product = cls.env["product.product"].create({
            "name": "Guard Route Other",
            "list_price": 12.0,
            "sale_ok": True,
            "is_published": True,
            "website_id": False,
        })
        params = cls.env["ir.config_parameter"].sudo()
        params.set_str("reza_cart_guard.enabled", "True")
        params.set_int("reza_cart_guard.hour_limit", 3)
        params.set_int("reza_cart_guard.day_limit", 20)
        params.set_int("reza_cart_guard.product_hour_limit", 2)
        cls.Attempt = cls.env["reza.website.cart.attempt"].sudo()
        cls.Order = cls.env["sale.order"].sudo()

    def setUp(self):
        super().setUp()
        self.Attempt.search([]).unlink()

    def _new_visitor(self):
        self.opener.cookies.clear()

    def _add(self, product, qty=1):
        return self.make_jsonrpc_request("/shop/cart/add", {
            "product_template_id": product.product_tmpl_id.id,
            "product_id": product.id,
            "quantity": qty,
        })

    def _cart_count(self):
        return self.Order.search_count([("order_line.product_id", "in", (self.product | self.other_product).ids)])

    def test_new_cart_under_limit_is_created(self):
        self._new_visitor()
        result = self._add(self.product)
        self.assertEqual(result.get("cart_quantity"), 1)
        self.assertEqual(self._cart_count(), 1)
        self.assertEqual(self.Attempt.search_count([]), 1)
        self.assertEqual(self.Attempt.search([]).product_id, self.product)

    def test_new_cart_over_limit_is_refused(self):
        # product_hour_limit = 2: two new carts for the product pass, the third is refused.
        for _i in range(2):
            self._new_visitor()
            self._add(self.product)
        self.assertEqual(self._cart_count(), 2)
        self._new_visitor()
        with self.assertRaises(JsonRpcException) as cm:
            self._add(self.product)
        self.assertIn("TooManyRequests", str(cm.exception))
        self.assertEqual(self._cart_count(), 2, "a refused request must not leave a cart")
        self.assertEqual(self.Attempt.search_count([]), 2)

        # hour_limit = 3: one more new cart for ANOTHER product passes, then any new cart is refused.
        self._new_visitor()
        self._add(self.other_product)
        self._new_visitor()
        with self.assertRaises(JsonRpcException) as cm:
            self._add(self.other_product)
        self.assertIn("TooManyRequests", str(cm.exception))
        self.assertEqual(self.Attempt.search_count([]), 3)

    def test_existing_cart_is_never_counted_or_blocked(self):
        self._new_visitor()
        self._add(self.product)
        cart_cookies = self.opener.cookies.copy()
        self.assertEqual(self.Attempt.search_count([]), 1)

        # A second visitor from the same address uses up the product limit.
        self._new_visitor()
        self._add(self.product)
        self._new_visitor()
        with self.assertRaises(JsonRpcException):
            self._add(self.product)

        # The first visitor keeps adding to the cart it already has, well past every limit.
        self.opener.cookies.clear()
        self.opener.cookies.update(cart_cookies)
        for _i in range(5):
            result = self._add(self.product)
        self._add(self.other_product)
        self.assertEqual(result.get("cart_quantity"), 6)
        self.assertEqual(self.Attempt.search_count([]), 2, "updates to an existing cart are not attempts")
        self.assertEqual(self._cart_count(), 2)

    def test_disabled_guard_does_not_refuse(self):
        self.env["ir.config_parameter"].sudo().set_str("reza_cart_guard.enabled", "off")
        for _i in range(3):
            self._new_visitor()
            self._add(self.product)
        self.assertEqual(self._cart_count(), 3)
        self.assertEqual(self.Attempt.search_count([]), 0)
