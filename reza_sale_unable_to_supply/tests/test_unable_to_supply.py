# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestUnableToSupply(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # The April database copy holds the company's bank account untrusted,
        # and posting an invoice then raises RedirectWarning. Production posts
        # invoices fine, so trust it inside the test transaction only.
        cls.company.partner_id.bank_ids.allow_out_payment = True
        cls.user = new_test_user(
            cls.env, login="reza_uts_staff",
            groups="sales_team.group_sale_manager,account.group_account_invoice,stock.group_stock_user",
            company_id=cls.company.id, company_ids=[cls.company.id],
        )
        cls.partner = cls.env["res.partner"].create({"name": "UTS Customer"})
        cls.tax = cls.env["account.tax"].create({
            "name": "UTS 10% incl",
            "amount": 10.0,
            "type_tax_use": "sale",
            "price_include_override": "tax_included",
            "company_id": cls.company.id,
        })
        Product = cls.env["product.product"]
        cls.nobbies = Product.create({
            "name": "UTS Nobbies", "type": "consu", "is_storable": True,
            "list_price": 24.99, "invoice_policy": "order", "taxes_id": [Command.set(cls.tax.ids)],
        })
        cls.thongs = Product.create({
            "name": "UTS Thongs", "type": "consu", "is_storable": True,
            "list_price": 22.99, "invoice_policy": "order", "taxes_id": [Command.set(cls.tax.ids)],
        })
        cls.shipping = Product.create({
            "name": "UTS Parcel Post", "type": "service",
            "list_price": 12.50, "invoice_policy": "order", "taxes_id": [Command.clear()],
        })

    # ----------------------------------------------------------------- helpers
    def _order(self, lines=None, confirm=True):
        lines = lines or [(self.nobbies, 1, 24.99), (self.thongs, 1, 22.99), (self.shipping, 1, 12.50)]
        order = self.env["sale.order"].with_user(self.user).create({
            "partner_id": self.partner.id,
            "order_line": [
                Command.create({"product_id": p.id, "product_uom_qty": q, "price_unit": price})
                for p, q, price in lines
            ],
        })
        if confirm:
            order.action_confirm()
        return order

    def _invoice(self, order):
        invoice = order._create_invoices()
        invoice.action_post()
        return invoice

    def _line(self, order, product):
        return order.order_line.filtered(lambda l: l.product_id == product)

    def _apply(self, order, qtys, user=None):
        wizard = self.env["reza.unable.supply.wizard"].with_user(user or self.user).with_context(
            default_order_id=order.id).create({})
        for wl in wizard.line_ids:
            wl.qty_to_remove = qtys.get(wl.sale_line_id.product_id, 0.0)
        return wizard.action_apply()

    def _refunds(self, order):
        return order.order_line.invoice_lines.move_id.filtered(lambda m: m.move_type == "out_refund")

    # ------------------------------------------------------------------- tests
    def test_wizard_offers_product_and_delivery_lines_only(self):
        order = self._order(lines=[(self.nobbies, 1, 24.99), (self.shipping, 1, 12.50)])
        order.order_line = [Command.create({"display_type": "line_note", "name": "a note"})]
        wizard = self.env["reza.unable.supply.wizard"].with_user(self.user).with_context(
            default_order_id=order.id).create({})
        self.assertEqual(wizard.line_ids.sale_line_id.product_id, self.nobbies | self.shipping)

    def test_invoiced_item_is_removed_and_credited(self):
        """The RKS00047 case: one item missing on an invoiced order."""
        order = self._order()
        invoice = self._invoice(order)
        self.assertAlmostEqual(invoice.amount_total, 60.48)

        action = self._apply(order, {self.nobbies: 1})

        nob = self._line(order, self.nobbies)
        self.assertEqual(nob.product_uom_qty, 0)
        self.assertTrue(all(m.state == "cancel" for m in nob.move_ids))
        thongs_moves = self._line(order, self.thongs).move_ids
        self.assertEqual(sum(thongs_moves.mapped("product_uom_qty")), 1)

        refund = self._refunds(order)
        self.assertEqual(len(refund), 1)
        self.assertEqual(action["res_id"], refund.id)
        self.assertEqual(refund.state, "posted")
        self.assertEqual(refund.reversed_entry_id, invoice)
        self.assertAlmostEqual(refund.amount_total, 24.99)
        self.assertEqual(refund.invoice_line_ids.product_id, self.nobbies)
        self.assertEqual(refund.invoice_line_ids.sale_line_ids, nob)
        # Matched against the original invoice, which keeps its full amount.
        self.assertTrue(refund.currency_id.is_zero(refund.amount_residual))
        self.assertAlmostEqual(invoice.amount_total, 60.48)
        self.assertAlmostEqual(invoice.amount_residual, 35.49)
        # Order reads fully invoiced: nothing to invoice, nothing to credit.
        self.assertEqual(nob.qty_invoiced, 0)
        self.assertTrue(all(l.qty_to_invoice == 0 for l in order.order_line))
        self.assertNotEqual(order.invoice_status, "to invoice")
        self.assertIn("Refund", order.message_ids[0].body)

    def test_uninvoiced_item_is_removed_without_credit_note(self):
        order = self._order()
        action = self._apply(order, {self.nobbies: 1})
        self.assertEqual(action["type"], "ir.actions.act_window_close")
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 0)
        self.assertFalse(self._refunds(order))
        self.assertAlmostEqual(self._invoice(order).amount_total, 35.49)

    def test_partial_quantity(self):
        order = self._order(lines=[(self.nobbies, 3, 24.99)])
        invoice = self._invoice(order)
        self._apply(order, {self.nobbies: 2})
        nob = self._line(order, self.nobbies)
        self.assertEqual(nob.product_uom_qty, 1)
        self.assertEqual(sum(nob.move_ids.filtered(lambda m: m.state != "cancel").mapped("product_uom_qty")), 1)
        refund = self._refunds(order)
        self.assertEqual(refund.invoice_line_ids.quantity, 2)
        self.assertAlmostEqual(refund.amount_total, 49.98)
        self.assertAlmostEqual(invoice.amount_residual, 24.99)
        self.assertEqual(nob.qty_invoiced, 1)

    def test_shipping_can_be_credited_too(self):
        order = self._order()
        self._invoice(order)
        self._apply(order, {self.nobbies: 1, self.thongs: 1, self.shipping: 1})
        refund = self._refunds(order)
        self.assertAlmostEqual(refund.amount_total, 60.48)
        self.assertEqual(len(refund.invoice_line_ids), 3)

    def test_paid_invoice_leaves_credit_note_open_for_refund_payment(self):
        """Mangrove Jacks / WhatYouNeed shape: the payment has a journal entry,
        so the invoice is already fully matched and the credit note stays open."""
        order = self._order()
        invoice = self._invoice(order)
        receivable = invoice.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
        misc = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.company.id)], limit=1)
        other = self.env["account.account"].search([
            ("company_ids", "in", self.company.id), ("account_type", "=", "asset_current"),
            ("deprecated", "=", False),
        ], limit=1)
        payment = self.env["account.move"].create({
            "journal_id": misc.id,
            "line_ids": [
                Command.create({"account_id": receivable.account_id.id, "partner_id": self.partner.id,
                                "credit": 60.48}),
                Command.create({"account_id": other.id, "debit": 60.48}),
            ],
        })
        payment.action_post()
        (receivable | payment.line_ids.filtered(lambda l: l.account_id == receivable.account_id)).reconcile()
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))

        self._apply(order, {self.nobbies: 1})
        refund = self._refunds(order)
        self.assertEqual(refund.state, "posted")
        self.assertAlmostEqual(refund.amount_residual, 24.99)
        self.assertIn("Register Payment", order.message_ids[0].body)

    def test_discount_leaves_credit_note_in_draft(self):
        order = self._order(lines=[(self.nobbies, 1, 24.99), (self.thongs, 1, 22.99),
                                   (self.shipping, 1, -5.00)])
        self._invoice(order)
        self._apply(order, {self.nobbies: 1})
        refund = self._refunds(order)
        self.assertEqual(refund.state, "draft")
        self.assertAlmostEqual(refund.amount_total, 24.99)
        self.assertIn("DRAFT", order.message_ids[0].body)

    def test_second_run_credits_only_what_is_left(self):
        order = self._order(lines=[(self.nobbies, 2, 24.99)])
        invoice = self._invoice(order)
        self._apply(order, {self.nobbies: 1})
        self._apply(order, {self.nobbies: 1})
        refunds = self._refunds(order)
        self.assertEqual(len(refunds), 2)
        self.assertAlmostEqual(sum(refunds.mapped("amount_total")), 49.98)
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))
        self.assertEqual(self._line(order, self.nobbies).qty_invoiced, 0)

    def test_cannot_remove_more_than_undelivered(self):
        order = self._order(lines=[(self.nobbies, 2, 24.99)])
        picking = order.picking_ids
        picking.move_ids.quantity = 1
        picking.move_ids.picked = True
        picking.with_context(cancel_backorder=False)._action_done()
        self.assertEqual(self._line(order, self.nobbies).qty_delivered, 1)
        with self.assertRaises(UserError) as cm:
            self._apply(order, {self.nobbies: 2})
        self.assertIn("at most 1", str(cm.exception))
        self._apply(order, {self.nobbies: 1})
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 1)

    def test_failure_changes_nothing(self):
        """A refusal part-way must leave the order exactly as it was."""
        order = self._order()
        invoice = self._invoice(order)
        with self.assertRaises(UserError) as cm:
            self._apply(order, {self.nobbies: 1, self.thongs: 5})
        self.assertIn("at most", str(cm.exception))
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 1)
        self.assertFalse(self._refunds(order))
        self.assertAlmostEqual(invoice.amount_residual, 60.48)

    def test_draft_invoice_blocks(self):
        order = self._order()
        order._create_invoices()
        with self.assertRaises(UserError) as cm:
            self._apply(order, {self.nobbies: 1})
        self.assertIn("draft invoice", str(cm.exception))
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 1)

    def test_locked_order_blocks(self):
        order = self._order()
        order.action_lock()
        with self.assertRaises(UserError) as cm:
            self._apply(order, {self.nobbies: 1})
        self.assertIn("is locked", str(cm.exception))

    def test_nothing_entered_blocks(self):
        order = self._order()
        with self.assertRaises(UserError):
            self._apply(order, {})

    def test_draft_order_blocks(self):
        order = self._order(confirm=False)
        with self.assertRaises(UserError):
            self._apply(order, {self.nobbies: 1})

    def test_needs_invoicing_rights(self):
        sales_only = new_test_user(
            self.env, login="reza_uts_sales_only",
            groups="sales_team.group_sale_manager,stock.group_stock_user",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        self.assertFalse(sales_only.has_group("account.group_account_invoice"))
        order = self._order()
        self._invoice(order)
        with self.assertRaises(AccessError) as cm:
            self._apply(order, {self.nobbies: 1}, user=sales_only)
        self.assertIn("Sales and Invoicing rights", str(cm.exception))
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 1)
        self.assertFalse(self._refunds(order))

    def test_cannot_remove_more_than_ordered_when_not_invoiced(self):
        """Nothing invoiced, nothing delivered: only the guard stops a
        negative ordered quantity."""
        order = self._order()
        with self.assertRaises(UserError) as cm:
            self._apply(order, {self.nobbies: 3})
        self.assertIn("at most 1", str(cm.exception))
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 1)

    def test_credit_skips_an_invoice_already_credited(self):
        """Two invoices for one line. The second removal must credit the OLDER
        invoice, because the newer one has already been credited in full."""
        order = self._order(lines=[(self.nobbies, 1, 24.99)])
        inv1 = self._invoice(order)
        self._line(order, self.nobbies).product_uom_qty = 2
        inv2 = self._invoice(order)
        self.assertNotEqual(inv1, inv2)

        self._apply(order, {self.nobbies: 1})
        first = self._refunds(order)
        self.assertEqual(first.reversed_entry_id, inv2)

        self._apply(order, {self.nobbies: 1})
        second = self._refunds(order) - first
        self.assertEqual(second.reversed_entry_id, inv1)
        self.assertTrue(inv1.currency_id.is_zero(inv1.amount_residual))
        self.assertTrue(inv2.currency_id.is_zero(inv2.amount_residual))
        self.assertTrue(second.currency_id.is_zero(second.amount_residual))

    def test_no_return_receipt_when_moves_cannot_merge(self):
        """The WYN00819 shape: the open delivery differs from what a fresh
        procurement would build (here, its deadline), so a negative
        procurement cannot merge into it and Odoo would raise a return receipt
        instead. The delivery itself must shrink, and no receipt appear."""
        order = self._order(lines=[(self.nobbies, 5, 24.99)])
        self._invoice(order)
        nob = self._line(order, self.nobbies)
        nob.move_ids.date_deadline = "2020-01-01 00:00:00"

        self._apply(order, {self.nobbies: 1})

        moves = self.env["stock.move"].search([("sale_line_id", "=", nob.id)])
        self.assertFalse(moves.filtered(lambda m: m.location_id.usage == "customer"),
                         "a return receipt was created")
        open_out = moves.filtered(lambda m: m.state not in ("done", "cancel"))
        self.assertEqual(sum(open_out.mapped("product_uom_qty")), 4)
        self.assertEqual(nob.product_uom_qty, 4)

    def test_whole_order_cancels_the_delivery(self):
        order = self._order()
        self._invoice(order)
        self._apply(order, {self.nobbies: 1, self.thongs: 1, self.shipping: 1})
        self.assertTrue(all(m.state == "cancel" for m in order.picking_ids.move_ids))
        self.assertEqual(order.picking_ids.state, "cancel")

    def test_picked_delivery_blocks(self):
        order = self._order()
        self._invoice(order)
        self._line(order, self.nobbies).move_ids.picked = True
        with self.assertRaises(UserError) as cm:
            self._apply(order, {self.nobbies: 1})
        self.assertIn("already picked", str(cm.exception))
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 1)
        self.assertFalse(self._refunds(order))

    def test_linked_edbert_purchase_blocks(self):
        if "reza_edbert_purchase_id" not in self.env["sale.order"]._fields:
            self.skipTest("reza_ecom_intercompany_po is not installed")
        order = self._order()
        self._invoice(order)
        vendor = self.env["res.partner"].create({"name": "UTS Edbert"})
        purchase = self.env["purchase.order"].create({
            "partner_id": vendor.id,
            "order_line": [Command.create({"product_id": self.nobbies.id, "product_qty": 1, "price_unit": 10})],
        })
        order.sudo().reza_edbert_purchase_id = purchase
        with self.assertRaises(UserError) as cm:
            self._apply(order, {self.nobbies: 1})
        self.assertIn("Edbert purchase", str(cm.exception))
        self.assertEqual(self._line(order, self.nobbies).product_uom_qty, 1)
