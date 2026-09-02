# -*- coding: utf-8 -*-
"""Cancelling a bridged purchase order must put the goods back.

The dangerous case is not the error path, it is the QUIET one: a validated
transfer cannot be un-validated, so cancelling paperwork on its own leaves the
goods sitting in the branch warehouse with nothing recording that they should
not be there. These check that the stock actually moves, not merely that a
return record was created.

The wholesale half is stubbed. It is a different database reached over
XML-RPC; what is tested here is the ecom side and the CONTRACT with the remote
one -- that the local return happens first, and that a refusal is a refusal.
"""
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCancelReturns(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.vendor = cls.env["res.partner"].create({"name": "TEST Edbert Holdings"})
        cls.product = cls.env["product.product"].create({
            "name": "TEST bridge product", "type": "consu", "is_storable": True,
            "standard_price": 3.36, "list_price": 10.0, "external_api_id": 105811,
        })
        cls.company.sudo().write({
            "external_api": True, "external_api_purchase": True,
            "external_api_url": "https://example.invalid", "external_api_db": "test-db",
            "external_api_username": "test", "external_api_password": "test",
            "external_api_partner_id": cls.vendor.id,
            "external_api_purchase_partner": 10399,
        })

    def _po(self, qty=4.0, remote_sale=987654):
        po = self.env["purchase.order"].create({
            "partner_id": self.vendor.id,
            "company_id": self.company.id,
            "external_api": True,
            "order_line": [(0, 0, {
                "product_id": self.product.id, "name": self.product.display_name,
                "product_qty": qty, "product_uom": self.product.uom_id.id,
                "price_unit": 3.36, "date_planned": "2026-09-02 00:00:00",
                "discount": 0.0,
            })],
        })
        po.external_api_sale = remote_sale
        return po

    def _receive(self, po):
        """Confirm and fully receive it, so stock really lands."""
        with patch.object(type(po), "get_external_api_sale", return_value=True):
            po.button_confirm()
        picking = po.picking_ids
        self.assertTrue(picking, "no receipt was created")
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(skip_backorder=True).button_validate()
        self.assertEqual(picking.state, "done")
        return picking

    def _stock_location(self):
        wh = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company.id)], limit=1)
        self.assertTrue(wh, "the test company has no warehouse")
        return wh.lot_stock_id

    def _on_hand(self):
        return self.env["stock.quant"]._get_available_quantity(
            self.product, self._stock_location())

    # -------------------------------------------------------------- the stock
    def test_returning_a_received_order_puts_the_goods_back(self):
        po = self._po(qty=4.0)
        picking = self._receive(po)
        before = self._on_hand()
        self.assertGreaterEqual(before, 4.0, "the receipt did not land")

        with patch.object(type(po), "_reza_remote", return_value=None), \
                patch.object(type(po), "_reza_return_remote", return_value=None):
            po.action_reza_return_to_edbert()

        self.assertEqual(self._on_hand(), before - 4.0,
                         "the goods must actually leave, not just gain a return record")
        self.assertTrue(picking.return_ids, "no return picking was created")
        self.assertEqual(picking.return_ids[0].state, "done",
                         "the return was created but never validated -- the stock would "
                         "still be on hand while the paperwork says otherwise")

    def test_cancel_refuses_once_the_goods_have_been_received(self):
        """Odoo will not cancel a purchase order with a done receipt, so the
        refusal must point at the button that CAN undo it rather than let core
        raise its own message with no way forward."""
        po = self._po(qty=4.0)
        self._receive(po)
        with self.assertRaises(UserError) as caught:
            po.button_cancel()
        self.assertIn("Return to Edbert", str(caught.exception))

    def test_a_cancel_with_nothing_received_still_works(self):
        po = self._po(qty=4.0)
        with patch.object(type(po), "get_external_api_sale", return_value=True):
            po.button_confirm()
        before = self._on_hand()
        with patch.object(type(po), "_reza_unlock_remote_sale", return_value=False), \
                patch.object(type(po), "cancel_external_api_sale", return_value=True):
            po.button_cancel()
        self.assertEqual(self._on_hand(), before, "nothing was received, so nothing may move")
        self.assertEqual(po.state, "cancel")

    # ------------------------------------------------------------- the refusals
    def test_it_refuses_to_return_goods_that_have_been_billed(self):
        po = self._po(qty=4.0)
        self._receive(po)
        with patch.object(type(po), "invoice_external_api_sale", return_value=True):
            po.action_create_invoice()
        self.assertTrue(po.invoice_ids, "fixture failed: no bill")
        with patch.object(type(po), "_reza_remote", return_value=None), \
                patch.object(type(po), "_reza_return_remote", return_value=None):
            with self.assertRaises(UserError) as caught:
                po.action_reza_return_to_edbert()
        self.assertIn("billed", str(caught.exception))

    def test_the_ecom_side_is_returned_before_the_wholesale_side(self):
        """Order matters: putting the goods back into Edbert while ecom still
        holds them is a DOUBLE COUNT, which is worse than a missing unit
        because a missing one is found at the next stocktake."""
        po = self._po(qty=2.0)
        self._receive(po)
        seen = []
        with patch.object(type(po), "_reza_return_local", autospec=True,
                          side_effect=lambda s, p: seen.append("local")), \
                patch.object(type(po), "_reza_return_remote", autospec=True,
                             side_effect=lambda s, i, n: seen.append("remote")), \
                patch.object(type(po), "_reza_remote", autospec=True, return_value=None):
            po.action_reza_return_to_edbert()
        self.assertEqual(seen[:1], ["local"], "the ecom receipt must be returned first")

    def test_the_return_button_is_not_reachable_without_the_purchase_group(self):
        """`groups=` on a view button hides it; it does not stop an RPC caller,
        and everything past this point moves real stock."""
        po = self._po(qty=1.0)
        plain = self.env["res.users"].create({
            "name": "TEST no purchase rights", "login": "test-no-purchase@example.invalid",
            # Odoo 18 calls this `groups_id`; `group_ids` is the 19 name and
            # raises ValueError: Invalid field 'group_ids' on model 'res.users'.
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(AccessError):
            po.with_user(plain).action_reza_return_to_edbert()
