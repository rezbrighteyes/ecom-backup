# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import UtsCommon


@tagged("post_install", "-at_install")
class TestExchange(UtsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env["product.product"]
        def make(name, price):
            return Product.create({
                "name": name, "type": "consu", "is_storable": True, "list_price": price,
                "invoice_policy": "order", "taxes_id": [Command.set(cls.tax.ids)],
            })
        cls.same = make("UTS Nobbies size 12", 24.99)
        cls.close = make("UTS Nobbies Deluxe", 25.49)    # +0.50: price kept
        cls.dear = make("UTS Nobbies Pro", 29.99)        # +5.00: customer owes
        cls.cheap = make("UTS Nobbies Lite", 19.99)      # -5.00: refund

    def _exchange(self, order, swaps, user=None):
        """swaps: {old_product: (qty, new_product)}"""
        wizard = self.env["reza.exchange.wizard"].with_user(user or self.user).with_context(
            default_order_id=order.id).create({})
        for wl in wizard.line_ids:
            if wl.product_id in swaps:
                qty, new = swaps[wl.product_id]
                wl.write({"qty_to_exchange": qty, "new_product_id": new.id})
        return wizard.action_apply()

    def _new_invoice(self, order, first):
        return order.invoice_ids.filtered(lambda m: m.move_type == "out_invoice") - first

    def _open_moves(self, line):
        return line.move_ids.filtered(lambda m: m.state not in ("done", "cancel"))

    def _pay_with_entry(self, invoice):
        """MJ / WYN shape: a payment that carries a journal entry."""
        rec = invoice.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
        misc = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.company.id)], limit=1)
        other = self.env["account.account"].search([
            ("company_ids", "in", self.company.id), ("account_type", "=", "asset_current"),
            ("deprecated", "=", False)], limit=1)
        pay = self.env["account.move"].create({"journal_id": misc.id, "line_ids": [
            Command.create({"account_id": rec.account_id.id, "partner_id": self.partner.id,
                            "credit": invoice.amount_total}),
            Command.create({"account_id": other.id, "debit": invoice.amount_total}),
        ]})
        pay.action_post()
        (rec | pay.line_ids.filtered(lambda l: l.account_id == rec.account_id)).reconcile()

    # ------------------------------------------------------------------ tests
    def test_uninvoiced_swap(self):
        order = self._order()
        self._exchange(order, {self.nobbies: (1, self.same)})
        old = self._line(order, self.nobbies)
        new = self._line(order, self.same)
        self.assertEqual(old.product_uom_qty, 0)
        self.assertFalse(self._open_moves(old))
        self.assertEqual(new.product_uom_qty, 1)
        self.assertEqual(sum(self._open_moves(new).mapped("product_uom_qty")), 1)
        # Same delivery, no second picking and no return receipt.
        self.assertEqual(len(order.picking_ids.filtered(lambda p: p.state != "cancel")), 1)
        self.assertFalse(order.picking_ids.move_ids.filtered(lambda m: m.location_id.usage == "customer"))
        self.assertFalse(order.invoice_ids)
        self.assertAlmostEqual(order.amount_total, 60.48)

    def test_invoiced_swap_same_price(self):
        order = self._order()
        first = self._invoice(order)
        self._exchange(order, {self.nobbies: (1, self.same)})
        refund = self._refunds(order)
        new_inv = self._new_invoice(order, first)
        self.assertEqual(refund.state, "posted")
        self.assertEqual(new_inv.state, "posted")
        self.assertAlmostEqual(refund.amount_total, 24.99)
        self.assertAlmostEqual(new_inv.amount_total, 24.99)
        self.assertEqual(new_inv.invoice_line_ids.product_id, self.same)
        # Matched to each other, the original untouched.
        self.assertTrue(refund.currency_id.is_zero(refund.amount_residual))
        self.assertTrue(new_inv.currency_id.is_zero(new_inv.amount_residual))
        self.assertAlmostEqual(first.amount_residual, 60.48)
        self.assertTrue(all(l.qty_to_invoice == 0 for l in order.order_line))
        self.assertIn("nothing to pay", order.message_ids[0].body)

    def test_price_kept_under_a_dollar(self):
        order = self._order()
        first = self._invoice(order)
        self._exchange(order, {self.nobbies: (1, self.close)})
        new = self._line(order, self.close)
        self.assertAlmostEqual(new.price_unit, 24.99)
        self.assertAlmostEqual(self._new_invoice(order, first).amount_total, 24.99)
        self.assertIn("price kept", order.message_ids[0].body)

    def test_dearer_item_customer_owes(self):
        order = self._order()
        first = self._invoice(order)
        self._exchange(order, {self.nobbies: (1, self.dear)})
        new_inv = self._new_invoice(order, first)
        self.assertAlmostEqual(new_inv.amount_total, 29.99)
        self.assertAlmostEqual(new_inv.amount_residual, 5.00)
        self.assertTrue(self._refunds(order).currency_id.is_zero(self._refunds(order).amount_residual))
        self.assertIn("owes", order.message_ids[0].body)

    def test_cheaper_item_refund(self):
        order = self._order()
        first = self._invoice(order)
        self._exchange(order, {self.nobbies: (1, self.cheap)})
        refund = self._refunds(order)
        self.assertAlmostEqual(refund.amount_residual, 5.00)
        self.assertTrue(refund.currency_id.is_zero(self._new_invoice(order, first).amount_residual))
        self.assertIn("Refund", order.message_ids[0].body)

    def test_paid_with_entry_still_matches(self):
        """Original fully paid by a journal-entry payment: the credit note has
        nothing to match on the original, and must land on the new invoice."""
        order = self._order()
        first = self._invoice(order)
        self._pay_with_entry(first)
        self._exchange(order, {self.nobbies: (1, self.same)})
        refund = self._refunds(order)
        new_inv = self._new_invoice(order, first)
        self.assertTrue(refund.currency_id.is_zero(refund.amount_residual))
        self.assertTrue(new_inv.currency_id.is_zero(new_inv.amount_residual))
        self.assertTrue(first.currency_id.is_zero(first.amount_residual))

    def test_partial_quantity(self):
        order = self._order(lines=[(self.nobbies, 3, 24.99)])
        first = self._invoice(order)
        self._exchange(order, {self.nobbies: (1, self.same)})
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 2)
        self.assertEqual(sum(self._open_moves(self._line(order, self.nobbies)).mapped("product_uom_qty")), 2)
        self.assertEqual(self._line(order, self.same).product_uom_qty, 1)
        self.assertAlmostEqual(self._new_invoice(order, first).amount_total, 24.99)

    def test_shipped_item_refused(self):
        order = self._order(lines=[(self.nobbies, 1, 24.99)])
        picking = order.picking_ids
        picking.move_ids.quantity = 1
        picking.move_ids.picked = True
        picking._action_done()
        with self.assertRaises(UserError) as cm:
            self._exchange(order, {self.nobbies: (1, self.same)})
        self.assertIn("at most", str(cm.exception))
        self.assertFalse(self._line(order, self.same))

    def test_same_product_refused(self):
        order = self._order()
        with self.assertRaises(UserError) as cm:
            self._exchange(order, {self.nobbies: (1, self.nobbies)})
        self.assertIn("same product", str(cm.exception))

    def test_missing_new_product_refused(self):
        order = self._order()
        wizard = self.env["reza.exchange.wizard"].with_user(self.user).with_context(
            default_order_id=order.id).create({})
        wizard.line_ids.filtered(lambda w: w.product_id == self.nobbies).qty_to_exchange = 1
        with self.assertRaises(UserError) as cm:
            wizard.action_apply()
        self.assertIn("Choose the new product", str(cm.exception))

    def test_other_lines_waiting_to_invoice_refused(self):
        order = self._order()
        self._invoice(order)
        self._line(order, self.thongs).product_uom_qty = 2   # 1 now waiting to invoice
        with self.assertRaises(UserError) as cm:
            self._exchange(order, {self.nobbies: (1, self.same)})
        self.assertIn("waiting to be invoiced", str(cm.exception))
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 1)

    def test_delivery_policy_product_refused_when_invoiced(self):
        order = self._order()
        self._invoice(order)
        self.same.invoice_policy = "delivery"
        with self.assertRaises(UserError) as cm:
            self._exchange(order, {self.nobbies: (1, self.same)})
        self.assertIn("invoiced on delivery", str(cm.exception))

    def test_discount_invoice_refused(self):
        order = self._order(lines=[(self.nobbies, 1, 24.99), (self.shipping, 1, -5.00)])
        self._invoice(order)
        with self.assertRaises(UserError) as cm:
            self._exchange(order, {self.nobbies: (1, self.same)})
        self.assertIn("discount", str(cm.exception))
        self.assertFalse(self._refunds(order))

    def test_needs_invoicing_rights(self):
        sales_only = new_test_user(
            self.env, login="reza_uts_ex_sales_only",
            groups="sales_team.group_sale_manager,stock.group_stock_user",
            company_id=self.company.id, company_ids=[self.company.id])
        order = self._order()
        with self.assertRaises(AccessError) as cm:
            self._exchange(order, {self.nobbies: (1, self.same)}, user=sales_only)
        self.assertIn("Sales and Invoicing rights", str(cm.exception))
        self.assertFalse(self._line(order, self.same))

    def test_printed_delivery_gets_a_second_one_and_says_so(self):
        order = self._order()
        order.picking_ids.printed = True
        self._exchange(order, {self.nobbies: (1, self.same)})
        new_picking = self._open_moves(self._line(order, self.same)).picking_id
        self.assertNotIn(new_picking, self._line(order, self.thongs).move_ids.picking_id)
        self.assertIn("separate delivery", order.message_ids[0].body)
        self.assertIn(new_picking.name, order.message_ids[0].body)

    def test_unprinted_delivery_takes_the_new_item(self):
        order = self._order()
        self._exchange(order, {self.nobbies: (1, self.same)})
        self.assertEqual(self._open_moves(self._line(order, self.same)).picking_id,
                         self._line(order, self.thongs).move_ids.picking_id)
        self.assertNotIn("separate delivery", order.message_ids[0].body)
