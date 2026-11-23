# -*- coding: utf-8 -*-
"""The shop may sell Edbert's free stock, less a buffer, on a fresh proved match.

Each test builds one storable product with "Continue selling" OFF and gives it
an Edbert figure the way the sync would. Nothing reaches the network.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.website_stock import PARAM_BUFFER, PARAM_STALE_HOURS

PARAM_LAST_SYNC = "reza_ecom_edbert_stock.last_sync"


@tagged("post_install", "-at_install")
class TestWebsiteSellable(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.product = cls.env["product.product"].create({
            "name": "Reza Edbert Gate Thong",
            "type": "consu",
            "is_storable": True,
            "allow_out_of_stock_order": False,
            "sale_ok": True,
        })
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.customers = cls.env.ref("stock.stock_location_customers")
        cls.params = cls.env["ir.config_parameter"].sudo()
        # Fixed settings, so a value already on the database copy cannot
        # change what the tests measure.
        cls.params.set_param(PARAM_BUFFER, "1")
        cls.params.set_param(PARAM_STALE_HOURS, "3")
        cls.params.set_param(PARAM_LAST_SYNC, fields.Datetime.now())

    def _edbert(self, qty, state="ok"):
        self.product.sudo().write({
            "reza_edbert_free_qty": qty,
            "reza_edbert_stock_state": state,
        })

    def _site_qty(self):
        return self.website._get_product_available_qty(self.product)

    def _own(self, qty):
        self.env["stock.quant"]._update_available_quantity(self.product, self.stock, qty)

    def _demand(self, qty, reserve=False):
        move = self.env["stock.move"].create({
            "name": "edbert gate demand",
            "product_id": self.product.id,
            "product_uom_qty": qty,
            "product_uom": self.product.uom_id.id,
            "location_id": self.stock.id,
            "location_dest_id": self.customers.id,
        })
        move._action_confirm()
        if reserve:
            move._action_assign()
        return move

    def test_site_sells_edbert_less_buffer(self):
        self._edbert(5)
        self.assertEqual(self._site_qty(), 4)

    def test_buffer_hides_the_last_unit(self):
        self._edbert(1)
        self.assertEqual(self._site_qty(), 0)

    def test_buffer_is_a_setting(self):
        self.params.set_param(PARAM_BUFFER, "0")
        self._edbert(5)
        self.assertEqual(self._site_qty(), 5)

    def test_stale_sync_ignores_edbert(self):
        self.params.set_param(
            PARAM_LAST_SYNC, fields.Datetime.now() - timedelta(hours=4))
        self._edbert(50)
        self.assertEqual(self._site_qty(), 0)

    def test_never_synced_ignores_edbert(self):
        self.params.search([("key", "=", PARAM_LAST_SYNC)]).unlink()
        self._edbert(50)
        self.assertEqual(self._site_qty(), 0)

    def test_unproved_match_ignores_edbert(self):
        self._edbert(50, state="no_match")
        self.assertEqual(self._site_qty(), 0)

    def test_own_stock_adds_to_edbert(self):
        self._own(1)
        self._edbert(3)
        self.assertEqual(self._site_qty(), 3)

    def test_figure_is_banded_from_five_up(self):
        for edbert, shown in ((6, 5), (11, 10), (21, 20), (5000, 20)):
            self._edbert(edbert)
            self.assertEqual(self._site_qty(), shown, "Edbert %s" % edbert)

    def test_cart_stops_at_the_band(self):
        self._edbert(5000)
        order = self.env["sale.order"].create({
            "partner_id": self.env.user.partner_id.id,
            "website_id": self.website.id,
        })
        allowed, _warning = order._verify_updated_quantity(
            self.env["sale.order.line"], self.product.id, 30)
        self.assertEqual(allowed, 20)

    def test_negative_own_stock_is_not_subtracted(self):
        self._own(-3)
        self._edbert(5)
        self.assertEqual(self._site_qty(), 4)

    def test_unshipped_orders_come_off_edbert(self):
        self._demand(3)
        self._edbert(5)
        self.assertEqual(self._site_qty(), 1)

    def test_reserved_demand_is_not_counted_twice(self):
        # 2 own units reserved for a 3-unit delivery: own free is 0, and only
        # the 1 unreserved unit still has to come from Edbert.
        self._own(2)
        move = self._demand(3, reserve=True)
        self.assertEqual(move.quantity, 2)
        self._edbert(5)
        self.assertEqual(self._site_qty(), 3)

    def _shipped(self, qty, status, approved=None):
        order = self.env["sale.order"].create({
            "partner_id": self.env.user.partner_id.id,
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": qty})],
        })
        vals = {"reza_edbert_status": status}
        if approved is not None:
            purchase = self.env["purchase.order"].create({
                "partner_id": self.env.user.partner_id.id,
            })
            purchase.date_approve = approved
            vals["reza_edbert_purchase_id"] = purchase.id
        order.sudo().write(vals)
        move = self.env["stock.move"].create({
            "name": "edbert gate shipped",
            "product_id": self.product.id,
            "product_uom_qty": qty,
            "product_uom": self.product.uom_id.id,
            "location_id": self.stock.id,
            "location_dest_id": self.customers.id,
            "sale_line_id": order.order_line.id,
        })
        move._action_confirm()
        move.quantity = qty
        move.picked = True
        move._action_done()
        self.assertEqual(move.state, "done")
        return move

    def test_shipped_before_edbert_order_is_subtracted(self):
        self._shipped(2, "pending")
        self._edbert(5)
        self.assertEqual(self._site_qty(), 2)

    def test_shipped_failed_edbert_order_is_subtracted(self):
        self._shipped(2, "failed")
        self._edbert(5)
        self.assertEqual(self._site_qty(), 2)

    def test_edbert_order_after_last_sync_is_subtracted(self):
        self._shipped(2, "raised", approved=fields.Datetime.now() + timedelta(minutes=5))
        self._edbert(5)
        self.assertEqual(self._site_qty(), 2)

    def test_edbert_order_seen_by_last_sync_is_not_subtracted_twice(self):
        self._shipped(2, "raised", approved=fields.Datetime.now() - timedelta(hours=2))
        self._edbert(5)
        self.assertEqual(self._site_qty(), 4)

    def test_order_not_bought_from_edbert_is_not_subtracted(self):
        self._shipped(2, "not_needed")
        self._edbert(5)
        self.assertEqual(self._site_qty(), 4)

    def test_shop_visitor_can_read_the_figure(self):
        self._edbert(5)
        public = self.env.ref("base.public_user")
        self.assertEqual(
            self.product.with_user(public)._reza_edbert_sellable_qty(0.0), 4)

    def test_cart_allows_up_to_the_sellable_qty(self):
        self._edbert(5)
        order = self.env["sale.order"].create({
            "partner_id": self.env.user.partner_id.id,
            "website_id": self.website.id,
        })
        allowed, warning = order._verify_updated_quantity(
            self.env["sale.order.line"], self.product.id, 10)
        self.assertEqual(allowed, 4)
        self.assertTrue(warning)

    def test_checkout_refuses_more_than_sellable(self):
        self._edbert(5)
        order = self.env["sale.order"].create({
            "partner_id": self.env.user.partner_id.id,
            "website_id": self.website.id,
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 6})],
        })
        with self.assertRaises(ValidationError) as cm:
            order._check_cart_is_ready_to_be_paid()
        self.assertIn("only 4", str(cm.exception))

    def test_continue_selling_products_are_untouched(self):
        self.product.allow_out_of_stock_order = True
        self._edbert(0)
        order = self.env["sale.order"].create({
            "partner_id": self.env.user.partner_id.id,
            "website_id": self.website.id,
        })
        allowed, _warning = order._verify_updated_quantity(
            self.env["sale.order.line"], self.product.id, 10)
        self.assertEqual(allowed, 10)
