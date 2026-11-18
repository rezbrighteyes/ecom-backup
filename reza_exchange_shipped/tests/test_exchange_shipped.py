# -*- coding: utf-8 -*-
"""Exchange (shipped) and the return to Edbert.

The fixture builds the real post-bridge state: a sale order delivered from
real stock, invoiced and paid, with its Edbert purchase confirmed, received and
billed. The wholesale database is a fake (_FakeEdbert) that keeps its own
state, so the tests can check what was created there and how many times.
"""
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.reza_sale_unable_to_supply.tests.common import UtsCommon

WID = 105811          # wholesale product id of `nobbies`
EDBERT_COST = 10.0    # Edbert's price, ex GST, on both sides


class _FakeEdbert:
    """The Edbert database, as far as reza.edbert.return talks to it."""

    def __init__(self, qty_delivered, price=EDBERT_COST):
        self.price = price
        self.qty_delivered = qty_delivered
        self.pickings = {500: {"id": 500, "name": "EBH/OUT/00001", "state": "done",
                               "picking_type_code": "outgoing", "return_id": False,
                               "origin": "P0001"}}
        self.moves = {}
        self.moves_qty = {}
        self.invoices = {700: {"id": 700, "name": "INV/EBH/0001", "state": "posted",
                               "move_type": "out_invoice", "journal_id": [1, "Sales"],
                               "ref": False, "qty": qty_delivered}}
        self.wizard_line_qty = 0.0
        self.created_returns = 0
        self.created_reversals = 0
        self.fail_on = None

    def execute_kw(self, db, uid, pwd, model, method, args, kw=None):
        if self.fail_on == (model, method):
            raise RuntimeError("Edbert said no to %s.%s" % (model, method))
        key = (model, method)
        if key == ("sale.order", "read"):
            return [{"id": args[0][0], "name": "EBH000001", "picking_ids": [500],
                     "invoice_ids": [700]}]
        if key == ("stock.picking", "search_read"):
            origin = [d for d in args[0] if d[0] == "origin"][0][2]
            return [dict(p) for p in self.pickings.values()
                    if p["origin"] == origin and p["state"] != "cancel"]
        if key == ("stock.picking", "read"):
            return [dict(self.pickings[i]) for i in args[0]]
        if key == ("stock.return.picking", "create"):
            return 900
        if key == ("stock.return.picking.line", "search_read"):
            return [{"id": 901, "product_id": [WID, "Nobbies"],
                     "move_quantity": self.qty_delivered},
                    {"id": 902, "product_id": [999, "Something else"], "move_quantity": 4.0}]
        if key == ("stock.return.picking.line", "write"):
            if args[0] == [901]:
                self.wizard_line_qty = args[1]["quantity"]
            return True
        if key == ("stock.return.picking", "action_create_returns"):
            self.created_returns += 1
            rid = 500 + self.created_returns
            self.pickings[rid] = {"id": rid, "name": "EBH/IN/%05d" % rid, "state": "assigned",
                                  "picking_type_code": "incoming", "return_id": 500,
                                  "origin": "EBH/OUT/00001"}
            self.moves[rid] = [{"id": rid * 10, "product_uom_qty": self.wizard_line_qty}]
            return {"res_id": rid}
        if key == ("stock.picking", "write"):
            self.pickings[args[0][0]].update(args[1])
            return True
        if key == ("stock.move", "search_read"):
            return self.moves[args[0][0][2]]
        if key == ("stock.move", "write"):
            self.moves_qty[args[0][0]] = args[1]["quantity"]
            return True
        if key == ("stock.picking", "button_validate"):
            self.pickings[args[0][0]]["state"] = "done"
            return True
        if key == ("account.move", "search_read"):
            ref = [d for d in args[0] if d[0] == "ref"][0][2]
            return [{"id": i["id"], "name": i["name"], "state": i["state"]} for i in self.invoices.values()
                    if i["move_type"] == "out_refund" and ref in (i["ref"] or "")
                    and i["state"] != "cancel"]
        if key == ("account.move", "read"):
            out = []
            for i in args[0]:
                inv = dict(self.invoices[i])
                inv["amount_untaxed"] = round(inv["qty"] * self.price, 2)
                out.append(inv)
            return out
        if key == ("account.move.reversal", "create"):
            self._reason = args[0]["reason"]
            return 950
        if key == ("account.move.reversal", "reverse_moves"):
            self.created_reversals += 1
            rid = 700 + self.created_reversals
            self.invoices[rid] = {"id": rid, "name": "RINV/EBH/%04d" % rid, "state": "draft",
                                  "move_type": "out_refund", "journal_id": [1, "Sales"],
                                  "ref": "Reversal of: INV/EBH/0001, %s" % self._reason,
                                  "qty": self.qty_delivered}
            return {"res_id": rid}
        if key == ("account.move.line", "search_read"):
            return [{"id": 7001, "product_id": [WID, "Nobbies"]},
                    {"id": 7002, "product_id": [999, "Something else"]}]
        if key == ("account.move", "write"):
            for cmd in args[1]["invoice_line_ids"]:
                if cmd[0] == 1:
                    self.invoices[args[0][0]]["qty"] = cmd[2]["quantity"]
            return True
        if key == ("account.move", "action_post"):
            self.invoices[args[0][0]]["state"] = "posted"
            return True
        raise AssertionError("unexpected remote call %s.%s" % key)


@tagged("post_install", "-at_install")
class TestExchangeShipped(UtsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user.groups_id |= cls.env.ref("purchase.group_purchase_user")
        cls.vendor = cls.env["res.partner"].create({"name": "TEST Edbert Holdings"})
        cls.company.sudo().write({
            "external_api": True, "external_api_purchase": True,
            "external_api_url": "https://example.invalid", "external_api_db": "test-db",
            "external_api_username": "test", "external_api_password": "test",
            "external_api_partner_id": cls.vendor.id, "external_api_purchase_partner": 10399,
        })
        cls.nobbies.write({"external_api_id": WID, "purchase_method": "receive"})
        cls.thongs.write({"external_api_id": 105812, "purchase_method": "receive"})
        Product = cls.env["product.product"]

        def make(name, price):
            return Product.create({
                "name": name, "type": "consu", "is_storable": True, "list_price": price,
                "invoice_policy": "order", "taxes_id": [Command.set(cls.tax.ids)],
            })
        cls.close = make("UTS Nobbies Deluxe", 25.49)    # +0.50: price kept
        cls.dear = make("UTS Nobbies Pro", 29.99)        # +5.00: customer owes
        cls.cheap = make("UTS Nobbies Lite", 19.99)      # -5.00: refund
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id

    def setUp(self):
        super().setUp()
        self.patch(self.env.cr, "commit", lambda *a, **k: None)

    # ----------------------------------------------------------------- helpers
    def _onhand(self, product):
        return sum(self.env["stock.quant"].search([
            ("product_id", "=", product.id), ("location_id", "child_of", self.stock.id),
        ]).mapped("quantity"))

    def _deliver(self, order):
        for line in order.order_line.filtered(lambda l: l.product_id.is_storable):
            self.env["stock.quant"]._update_available_quantity(
                line.product_id, self.stock, line.product_uom_qty)
        for picking in order.picking_ids:
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.button_validate()
            self.assertEqual(picking.state, "done")

    def _pay(self, invoice):
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

    def _edbert_purchase(self, order):
        """What the bridge leaves behind: a confirmed, received, billed purchase."""
        lines = order.order_line.filtered(lambda l: l.product_id.is_storable)
        purchase = self.env["purchase.order"].create({
            "partner_id": self.vendor.id, "company_id": self.company.id,
            "origin": order.name, "external_api": True,
            "order_line": [Command.create({
                "product_id": l.product_id.id, "name": l.product_id.display_name,
                "product_qty": l.qty_delivered, "product_uom": l.product_uom.id,
                "price_unit": EDBERT_COST, "date_planned": order.date_order,
                "discount": 0.0, "taxes_id": [Command.clear()],
            }) for l in lines],
        })

        def _push(purchases):
            purchases.filtered(lambda p: not p.external_api_sale).write(
                {"external_api_sale": 987654})
            return True
        with patch.object(type(purchase), "get_external_api_sale", autospec=True,
                          side_effect=_push):
            purchase.button_confirm()
        for picking in purchase.picking_ids:
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.button_validate()
        # d3_external_api's action_create_invoice asks wholesale to invoice
        # too; that remote leg is not what these tests are about.
        with patch.object(type(purchase), "invoice_external_api_sale", return_value=True):
            purchase.action_create_invoice()
        bill = purchase.invoice_ids
        bill.invoice_date = bill.date or "2026-11-12"
        bill.action_post()
        order.sudo().write({
            "reza_edbert_purchase_id": purchase.id, "reza_edbert_status": "raised",
            "reza_edbert_transfer_done": True, "reza_edbert_invoiced": True,
        })
        return purchase

    def _shipped(self, paid=True, edbert=True, carrier=None):
        order = self._order(lines=[(self.nobbies, 2, 24.99), (self.thongs, 1, 22.99)])
        if carrier:
            order.set_delivery_line(carrier, 12.50)
        self._deliver(order)
        invoice = self._invoice(order)
        if paid:
            self._pay(invoice)
        purchase = self._edbert_purchase(order) if edbert else None
        return order, invoice, purchase

    def _fake(self, **kw):
        fake = _FakeEdbert(qty_delivered=2.0, **kw)
        self.patch(type(self.env["purchase.order"]), "_reza_remote",
                   lambda self: (fake, "db", 1, "pwd"))
        return fake

    def _exchange(self, order, swaps, user=None, charge_shipping=True):
        """swaps: {old_product: (qty, new_product)}"""
        wizard = self.env["reza.exchange.shipped.wizard"].with_user(user or self.user) \
            .with_context(default_order_id=order.id).create({"charge_shipping": charge_shipping})
        for wl in wizard.line_ids:
            if wl.product_id in swaps:
                qty, new = swaps[wl.product_id]
                wl.write({"qty_to_exchange": qty, "new_product_id": new.id})
        return wizard.action_apply()

    def _new_order(self, order):
        return self.env["sale.order"].search([("reza_exchange_origin_id", "=", order.id)])

    def _refund(self, order):
        return order.invoice_ids.filtered(lambda m: m.move_type == "out_refund")

    # ----------------------------------------------------- the customer side
    def test_same_product_replacement(self):
        order, first, __ = self._shipped()
        before = self._onhand(self.nobbies)
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        old = self._line(order, self.nobbies)
        self.assertEqual(old.qty_delivered, 1, "the customer return did not land")
        self.assertEqual(old.product_uom_qty, 1, "the ordered quantity was not lowered")
        self.assertEqual(self._onhand(self.nobbies), before + 1, "the item is not back in stock")
        new = self._new_order(order)
        self.assertEqual(len(new), 1)
        self.assertEqual(new.state, "sale")
        self.assertEqual(new.order_line.product_id, self.nobbies)
        self.assertEqual(new.order_line.product_uom_qty, 1)
        self.assertEqual(new.warehouse_id, order.warehouse_id)
        self.assertEqual(new.reza_edbert_status, "pending",
                         "the bridge will not buy the replacement")
        refund = self._refund(order)
        new_inv = new.invoice_ids
        self.assertEqual(refund.state, "posted")
        self.assertEqual(new_inv.state, "posted")
        self.assertAlmostEqual(refund.amount_total, 24.99)
        self.assertTrue(refund.currency_id.is_zero(refund.amount_residual))
        self.assertTrue(new_inv.currency_id.is_zero(new_inv.amount_residual))
        self.assertIn("nothing to pay", order.message_ids[0].body)

    def _carrier(self):
        product = self.env["product.product"].create({
            "name": "UTS Parcel Post carrier", "type": "service", "list_price": 12.50,
            "invoice_policy": "order", "taxes_id": [Command.clear()]})
        return self.env["delivery.carrier"].create({
            "name": "UTS Parcel Post", "delivery_type": "fixed", "fixed_price": 12.50,
            "product_id": product.id})

    def test_shipping_charged_again_by_default(self):
        carrier = self._carrier()
        order, __, __ = self._shipped(carrier=carrier)
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        new = self._new_order(order)
        ship = new.order_line.filtered("is_delivery")
        self.assertEqual(new.carrier_id, carrier)
        self.assertAlmostEqual(ship.price_total, 12.50)
        # Same item, so the only thing the customer owes is the shipping.
        self.assertAlmostEqual(new.invoice_ids.amount_total, 24.99 + 12.50)
        self.assertAlmostEqual(new.invoice_ids.amount_residual, 12.50)
        self.assertIn("owes", order.message_ids[0].body)
        self.assertEqual(new.picking_ids.carrier_id, carrier)

    def test_shipping_not_charged_when_unticked(self):
        carrier = self._carrier()
        order, __, __ = self._shipped(carrier=carrier)
        self._exchange(order, {self.nobbies: (1, self.nobbies)}, charge_shipping=False)
        new = self._new_order(order)
        self.assertFalse(new.order_line.filtered("is_delivery"))
        self.assertEqual(new.carrier_id, carrier, "the replacement must still ship")
        self.assertTrue(new.currency_id.is_zero(new.invoice_ids.amount_residual))

    def test_price_kept_under_a_dollar(self):
        order, __, __ = self._shipped()
        self._exchange(order, {self.nobbies: (1, self.close)})
        new = self._new_order(order)
        self.assertAlmostEqual(new.order_line.price_unit, 24.99)
        self.assertTrue(new.currency_id.is_zero(new.invoice_ids.amount_residual))
        self.assertIn("price kept", order.message_ids[0].body)

    def test_dearer_item_customer_owes(self):
        order, __, __ = self._shipped()
        self._exchange(order, {self.nobbies: (1, self.dear)})
        inv = self._new_order(order).invoice_ids
        self.assertAlmostEqual(inv.amount_total, 29.99)
        self.assertAlmostEqual(inv.amount_residual, 5.00)
        self.assertIn("owes", order.message_ids[0].body)

    def test_cheaper_item_refund(self):
        order, __, __ = self._shipped()
        self._exchange(order, {self.nobbies: (1, self.cheap)})
        refund = self._refund(order)
        self.assertAlmostEqual(refund.amount_residual, 5.00)
        self.assertTrue(refund.currency_id.is_zero(self._new_order(order).invoice_ids.amount_residual))
        self.assertIn("Refund", order.message_ids[0].body)

    def test_more_than_delivered_is_refused(self):
        order, __, __ = self._shipped()
        with self.assertRaises(UserError) as cm:
            self._exchange(order, {self.nobbies: (3, self.nobbies)})
        self.assertIn("only 2.0 was delivered", str(cm.exception))
        self.assertFalse(self._new_order(order))

    def test_no_replacement_is_refused(self):
        order, __, __ = self._shipped()
        wizard = self.env["reza.exchange.shipped.wizard"].with_user(self.user) \
            .with_context(default_order_id=order.id).create({})
        wizard.line_ids.filtered(lambda l: l.product_id == self.nobbies).qty_to_exchange = 1
        with self.assertRaises(UserError) as cm:
            wizard.action_apply()
        self.assertIn("Choose the replacement", str(cm.exception))

    def test_needs_inventory_rights(self):
        order, __, __ = self._shipped()
        clerk = new_test_user(
            self.env, login="exs_no_stock",
            groups="sales_team.group_sale_salesman_all_leads,account.group_account_invoice",
            company_id=self.company.id, company_ids=[self.company.id])
        with self.assertRaises(AccessError) as cm:
            self._exchange(order, {self.nobbies: (1, self.nobbies)}, user=clerk)
        self.assertIn("Inventory rights", str(cm.exception))

    def test_edbert_unfinished_is_refused(self):
        order, __, __ = self._shipped()
        order.sudo().reza_edbert_invoiced = False
        self._fake()
        with self.assertRaises(UserError) as cm:
            self._exchange(order, {self.nobbies: (1, self.nobbies)})
        self.assertIn("is not finished yet", str(cm.exception))

    def test_edbert_not_raised_is_refused(self):
        order, __, __ = self._shipped(edbert=False)
        order.sudo().reza_edbert_status = "pending"
        with self.assertRaises(UserError) as cm:
            self._exchange(order, {self.nobbies: (1, self.nobbies)})
        self.assertIn("is not raised yet", str(cm.exception))

    def test_not_an_edbert_order_queues_nothing(self):
        order, __, __ = self._shipped(edbert=False)
        order.sudo().reza_edbert_status = "not_needed"
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        self.assertTrue(self._new_order(order))
        self.assertFalse(order.reza_edbert_return_ids)

    def test_cannot_supply_still_refuses_after_edbert(self):
        """The bypass is for this flow only. Cannot Supply on its own -- the
        public action_apply a client can call -- must still refuse an order
        whose Edbert purchase is raised."""
        order, __, __ = self._shipped()
        with self.assertRaises(UserError) as cm:
            self._apply(order, {self.nobbies: 1})
        self.assertIn("is already raised", str(cm.exception))
        self.assertNotIn("reza_edbert_handled", self.env["reza.unable.supply.wizard"]._fields,
                         "a client-settable skip flag is back on the wizard")

    # --------------------------------------------------------- the Edbert side
    def test_edbert_return_happy_path(self):
        order, __, purchase = self._shipped()
        fake = self._fake()
        before = self._onhand(self.nobbies)
        self._exchange(order, {self.nobbies: (1, self.dear)})
        row = order.reza_edbert_return_ids
        self.assertEqual(len(row), 1)
        self.assertEqual((row.product_id, row.qty, row.state), (self.nobbies, 1, "pending"))
        self.env["reza.edbert.return"]._cron_process()
        self.assertEqual(row.state, "done", row.note)
        # The warehouse ends where it started: in from the customer, out to Edbert.
        self.assertEqual(self._onhand(self.nobbies), before)
        self.assertEqual(row.local_return_id.state, "done")
        pol = purchase.order_line.filtered(lambda l: l.product_id == self.nobbies)
        self.assertEqual(pol.qty_received, 1)
        # The vendor credit is tied to the purchase line, so the purchase
        # order does not go on showing a bill to receive.
        self.assertEqual(pol.qty_invoiced, 1)
        # Edbert: one return of exactly 1, validated; one credit note of 1, posted.
        self.assertEqual(fake.created_returns, 1)
        self.assertEqual(fake.wizard_line_qty, 1)
        self.assertEqual(fake.pickings[501]["state"], "done")
        self.assertEqual(fake.invoices[701]["qty"], 1)
        self.assertEqual(fake.invoices[701]["state"], "posted")
        # Ecom: a vendor credit for 1 at Edbert's price, posted, carrying their number.
        vc = row.vendor_refund_id
        self.assertEqual(vc.move_type, "in_refund")
        self.assertEqual(vc.state, "posted")
        self.assertAlmostEqual(vc.amount_untaxed, EDBERT_COST)
        self.assertEqual(vc.ref, "RINV/EBH/0701")
        self.assertIn("went back to Edbert", order.message_ids[0].body)

    def test_credits_that_disagree_post_neither(self):
        order, __, __ = self._shipped()
        fake = self._fake(price=EDBERT_COST + 1)
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        row = order.reza_edbert_return_ids
        self.env["reza.edbert.return"]._cron_process()
        self.assertEqual(row.state, "mismatch")
        self.assertEqual(row.vendor_refund_id.state, "draft")
        self.assertEqual(fake.invoices[701]["state"], "draft")
        self.assertIn("Neither was posted", row.note)

    def test_rounding_gap_follows_edbert(self):
        """RKS00086: Edbert keeps 2-decimal prices, ecom the bridge's, so the
        same units come out a few cents apart. The credit follows Edbert."""
        order, __, __ = self._shipped()
        fake = self._fake(price=EDBERT_COST + 0.05)   # 0.5 %: rounding, not a real gap
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        row = order.reza_edbert_return_ids
        self.env["reza.edbert.return"]._cron_process()
        self.assertEqual(row.state, "done", row.note)
        self.assertAlmostEqual(row.vendor_refund_id.amount_untaxed, EDBERT_COST + 0.05)
        self.assertEqual(row.vendor_refund_id.state, "posted")
        self.assertEqual(fake.invoices[701]["state"], "posted")

    def test_failure_resumes_without_repeating(self):
        order, __, __ = self._shipped()
        fake = self._fake()
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        row = order.reza_edbert_return_ids
        fake.fail_on = ("account.move.reversal", "create")
        self.env["reza.edbert.return"]._cron_process()
        self.assertEqual(row.state, "failed")
        self.assertEqual(row.attempts, 1)
        self.assertIn("Edbert said no", row.note)
        # Steps before the failure are recorded, so they are not repeated.
        self.assertTrue(row.local_return_id)
        self.assertTrue(row.remote_return_name)
        self.assertTrue(row.vendor_refund_id)
        local, vendor = row.local_return_id, row.vendor_refund_id
        fake.fail_on = None
        self.env["reza.edbert.return"]._cron_process()
        self.assertEqual(row.state, "done", row.note)
        self.assertEqual(fake.created_returns, 1, "a second Edbert return was created")
        self.assertEqual(fake.created_reversals, 1)
        self.assertEqual(row.local_return_id, local)
        self.assertEqual(row.vendor_refund_id, vendor)

    def test_remote_return_found_by_marker_is_adopted(self):
        """A run that died after Edbert created the return, before ecom
        recorded it, must adopt that return and not create another."""
        order, __, __ = self._shipped()
        fake = self._fake()
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        row = order.reza_edbert_return_ids
        fake.pickings[560] = {"id": 560, "name": "EBH/IN/00560", "state": "done",
                              "picking_type_code": "incoming", "return_id": 500,
                              "origin": row._get_marker()}
        self.env["reza.edbert.return"]._cron_process()
        self.assertEqual(row.state, "done", row.note)
        self.assertEqual(fake.created_returns, 0)
        self.assertEqual(row.remote_return_name, "EBH/IN/00560")

    def test_remote_credit_found_by_marker_is_adopted(self):
        """Edbert created the credit note, then the run died before ecom
        recorded it. The next run must find it by its marker."""
        order, __, __ = self._shipped()
        fake = self._fake()
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        row = order.reza_edbert_return_ids
        fake.fail_on = ("account.move", "write")
        self.env["reza.edbert.return"]._cron_process()
        self.assertEqual(row.state, "failed")
        self.assertEqual(fake.created_reversals, 1)
        self.assertFalse(row.remote_refund_id)
        # It died before the quantity was cut: the adopted credit note still
        # carries the full 2, and must be cut to 1 on adoption.
        self.assertEqual(fake.invoices[701]["qty"], 2)
        fake.fail_on = None
        self.env["reza.edbert.return"]._cron_process()
        self.assertEqual(row.state, "done", row.note)
        self.assertEqual(fake.created_reversals, 1, "a second Edbert credit note was created")
        self.assertEqual(row.remote_refund_id, 701)
        self.assertEqual(fake.invoices[701]["qty"], 1)

    def test_exhausted_rows_are_not_retried(self):
        order, __, __ = self._shipped()
        fake = self._fake()
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        row = order.reza_edbert_return_ids
        row.sudo().write({"state": "failed", "attempts": 5})
        self.env["reza.edbert.return"]._cron_process()
        self.assertEqual(row.state, "failed")
        self.assertEqual(fake.created_returns, 0)

    def test_retry_needs_purchase_rights(self):
        order, __, __ = self._shipped()
        self._fake()
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        row = order.reza_edbert_return_ids
        clerk = new_test_user(
            self.env, login="exs_sales_only", groups="sales_team.group_sale_salesman",
            company_id=self.company.id, company_ids=[self.company.id])
        with self.assertRaises(AccessError) as cm:
            row.with_user(clerk).action_retry()
        self.assertIn("Only Purchase users", str(cm.exception))
        with self.assertRaises(AccessError):
            self.env["reza.edbert.return"].with_user(clerk)._cron_process()

    def test_cron_runs_as_superuser_without_the_group(self):
        """The env.su leg of the guard: a superuser env whose user is NOT in
        the purchase group must still run (the cron's shape)."""
        order, __, __ = self._shipped()
        self._fake()
        self._exchange(order, {self.nobbies: (1, self.nobbies)})
        plain = new_test_user(self.env, login="exs_plain", groups="base.group_user",
                              company_id=self.company.id, company_ids=[self.company.id])
        self.assertFalse(plain.has_group("purchase.group_purchase_user"))
        self.env(user=plain, su=True)["reza.edbert.return"]._cron_process()
        self.assertEqual(order.reza_edbert_return_ids.state, "done")
