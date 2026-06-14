from odoo.tests.common import TransactionCase


class TestWebsiteCartAttempt(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].create({"name": "Cart Guard Test"})
        cls.product = cls.env["product.product"].create({"name": "Guarded Product"})
        cls.Attempt = cls.env["reza.website.cart.attempt"]

    def _check(self, **overrides):
        values = {
            "website_id": self.website.id,
            "ip_hash": "test-ip-hash",
            "product_id": self.product.id,
            "hour_limit": 6,
            "day_limit": 20,
            "product_hour_limit": 3,
        }
        values.update(overrides)
        return self.Attempt.check_and_record(**values)

    def test_repeated_product_cart_creation_is_limited(self):
        self.assertTrue(self._check())
        self.assertTrue(self._check())
        self.assertTrue(self._check())
        self.assertFalse(self._check())
        self.assertEqual(self.Attempt.search_count([]), 3)

    def test_total_hourly_cart_creation_is_limited(self):
        self.assertTrue(self._check(hour_limit=1, product_hour_limit=3))
        other_product = self.env["product.product"].create({"name": "Other Product"})
        self.assertFalse(
            self._check(
                product_id=other_product.id,
                hour_limit=1,
                product_hour_limit=3,
            )
        )
