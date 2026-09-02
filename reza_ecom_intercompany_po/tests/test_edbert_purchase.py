# -*- coding: utf-8 -*-
"""What these guard, in order of how much they hurt when they break.

1. The Edbert cost must survive `purchase.order.line.create`. `price_unit`,
   `name`, `date_planned` and `discount` are one stored compute group -- supply
   three and Odoo assigns all four, replacing the price. That fault is invisible
   in the data (a plausible price is still there) and only shows up as an
   intercompany overcharge weeks later.
2. A retry must never create a SECOND wholesale sale order. `d3_external_api`
   stamps `purchase.external_api_sale` with no commit behind it, so a failure
   after the remote create rolls the stamp away while the remote order survives.
3. A failure must stay visible and be retried, never be recorded as a success.
4. Confirming a sale must never fail because of anything this module does.
5. The quantity must be in the same unit the sale line used.

`get_external_api_sale` is stubbed rather than `button_confirm`, so the REAL
`button_confirm` runs and the state really advances -- stubbing button_confirm
leaves every order in `draft` and makes the status assertions meaningless. The
remote reads are stubbed too: these are unit tests of OUR logic, not of the
wholesale connection, which is proven separately by an actual order.

NOTE ON COMMITS. Odoo 18 `TransactionCase.setUpClass` replaces `cr.commit`,
`cr.rollback` and `cr.close` with `forbidden()` (`odoo/tests/common.py`), so any
test reaching this module's deliberate commit-before-confirm dies with
"Cannot commit or rollback a cursor from inside a test". A `TestCursor`, where
commit would merely reopen a savepoint, is only installed by
`registry.enter_test_mode()`, which `HttpCase` calls and `TransactionCase` does
not -- an earlier version of this docstring had that backwards, and the seven
tests that create or confirm a purchase order all failed on it.

`setUp` therefore neutralises `commit` for the duration. The consequence is
unchanged and worth restating: the ORDERING of the commit relative to the remote
call is NOT exercised by any test here. Its correctness rests on reading.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models.sale_order import MAX_ATTEMPTS


@tagged("post_install", "-at_install")
class TestEdbertPurchase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.vendor = cls.env["res.partner"].create({"name": "TEST Edbert Holdings"})
        cls.customer = cls.env["res.partner"].create({"name": "TEST ecom customer"})
        cls.product = cls.env["product.product"].create({
            "name": "TEST bridge product",
            "type": "consu",
            "is_storable": True,
            "standard_price": 99.99,          # ecom's own cost -- must NOT be used
            "list_price": 150.0,
            "external_api_id": 105811,        # the wholesale id
        })
        # The company must look configured, or the worker exits early.
        cls.company.sudo().write({
            "external_api": True,
            "external_api_purchase": True,
            "external_api_url": "https://example.invalid",
            "external_api_db": "test-db",
            "external_api_username": "test",
            "external_api_password": "test",
            "external_api_partner_id": cls.vendor.id,
            "external_api_purchase_partner": 10399,
        })

    def setUp(self):
        super().setUp()
        # See the module docstring. The worker commits on purpose, and Odoo 18
        # forbids that inside a test; without this, every test that creates or
        # confirms a purchase order fails on the cursor rather than on its own
        # assertion.
        self.patch(self.env.cr, "commit", lambda *a, **k: None)

    def _order(self, qty=3.0, uom=None, company=None):
        vals = {
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": qty,
                **({"product_uom": uom.id} if uom else {}),
            })],
        }
        if company:
            # Set at CREATE. Writing company_id onto an order that already has
            # lines runs _check_company against the pricelist and the taxes.
            vals["company_id"] = company.id
        return self.env["sale.order"].with_company(company or self.company).create(vals)

    def _raise(self, order, costs=None, remote=None):
        """Run the worker with the two remote calls stubbed out.

        `get_external_api_sale` is the vendor hook inside `button_confirm`, so
        stubbing it lets the real confirm run and the state really advance.
        The stub also STAMPS `external_api_sale`, because the real one does
        (`d3_external_api/models/purchase_order.py:56`) and the module now
        treats a confirmed order carrying no stamp as one that was never
        pushed. A stub that skipped it would make every test look like that
        fault.
        """
        def _push(purchases):
            # The real one returns early on an already-stamped order and calls
            # confirm_external_api_sale() instead of creating a second remote
            # order (`d3_external_api/models/purchase_order.py:43-45`). A stub
            # that overwrote the stamp would destroy the very link the recovery
            # path had just restored.
            purchases.filtered(lambda p: not p.external_api_sale).write(
                {"external_api_sale": 987654})
            return True

        Purchase = type(self.env["purchase.order"])
        with patch.object(type(order), "_reza_edbert_costs",
                          return_value=costs if costs is not None else {105811: 3.3610}), \
                patch.object(type(order), "_reza_find_remote_sale",
                             return_value=remote), \
                patch.object(Purchase, "get_external_api_sale", autospec=True,
                             side_effect=_push):
            return order._reza_raise_edbert_purchase()


    def _draft_purchase(self, order, qty=3.0):
        """A draft purchase order already linked to `order`.

        Built directly rather than by confirming one and writing `state` back:
        a real confirm creates a receipt picking, and re-confirming after a
        hand-written state would leave a second one behind.
        """
        purchase = self.env["purchase.order"].create({
            "partner_id": self.vendor.id,
            "company_id": self.company.id,
            "origin": order.name,
            "external_api": True,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "name": self.product.display_name,
                "product_qty": qty,
                "product_uom": self.product.uom_id.id,
                "price_unit": 3.3610,
                "date_planned": order.date_order,
                "discount": 0.0,
            })],
        })
        order._reza_mark("failed", "an earlier pass died in the push", purchase)
        self.assertEqual(purchase.state, "draft")
        return purchase

    # ------------------------------------------------------------------ price
    def test_edbert_cost_survives_the_create(self):
        """The whole point of the module: Edbert's cost, not ecom's."""
        order = self._order()
        order.action_confirm()
        purchase = self._raise(order)
        self.assertTrue(purchase, "no purchase order was raised")
        line = purchase.order_line
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(
            line.price_unit, 3.3610, places=4,
            msg="the Edbert cost was replaced -- most likely the price_unit / name / "
                "date_planned / discount compute group ran because one of them was "
                "missing from the create vals",
        )
        self.assertNotAlmostEqual(
            line.price_unit, 99.99, places=2,
            msg="ecom's own standard_price was used instead of Edbert's",
        )
        self.assertEqual(purchase.state, "purchase",
                         "the stub should have let the real confirm run")
        self.assertEqual(order.reza_edbert_status, "raised")
        self.assertEqual(order.reza_edbert_purchase_id, purchase)

    # --------------------------------------------------------------- quantity
    def test_quantity_keeps_the_sale_line_unit(self):
        order = self._order(qty=7.0)
        order.action_confirm()
        purchase = self._raise(order, costs={105811: 1.0})
        self.assertAlmostEqual(purchase.order_line.product_qty, 7.0)
        self.assertEqual(purchase.order_line.product_uom,
                         order.order_line.product_uom,
                         "the purchase line must use the same unit as the sale line")

    # ------------------------------------------------------------- never block
    def test_confirm_still_works_when_the_bridge_cannot(self):
        """A broken bridge must cost nobody their order."""
        self.company.sudo().write({"external_api_url": False, "external_api_db": False})
        order = self._order()
        order.action_confirm()                       # must not raise
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.reza_edbert_status, "pending",
                         "it should still be queued, so it heals when the settings return")

    def test_a_zero_edbert_cost_is_refused_not_ordered(self):
        order = self._order()
        order.action_confirm()
        self._raise(order, costs={105811: 0.0})
        self.assertEqual(order.reza_edbert_status, "failed")
        self.assertFalse(order.reza_edbert_purchase_id,
                         "a zero cost must not become a purchase order")

    def test_an_archived_wholesale_product_is_refused(self):
        order = self._order()
        order.action_confirm()
        self._raise(order, costs={105811: "archived"})
        self.assertEqual(order.reza_edbert_status, "failed")
        self.assertIn("archived", order.reza_edbert_note or "")

    def test_an_unmapped_product_fails_rather_than_going_quiet(self):
        """A missing external_api_id is a mapping GAP, not a decision.

        Marking it `not_needed` would drop it out of the cron domain for good
        and hide it -- post-catalogue-rebuild products carry external_api_id 0,
        so this happens for real.
        """
        self.product.external_api_id = 0
        order = self._order()
        order.action_confirm()
        self._raise(order)
        self.assertEqual(order.reza_edbert_status, "failed")
        self.assertIn("not mapped", order.reza_edbert_note or "")
        self.assertEqual(order.reza_edbert_attempts, 1,
                         "it must be retried, so the counter has to move")

    def test_an_order_with_nothing_physical_is_not_a_failure(self):
        """Services and combos are not bought from Edbert. Marking such an order
        `failed` puts a red banner on a correct order and retries it five times.
        It is only a failure when buyable lines EXIST and none is mapped."""
        service = self.env["product.product"].create({
            "name": "TEST delivery service", "type": "service", "list_price": 9.0})
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": service.id, "product_uom_qty": 1.0})],
        })
        order.action_confirm()
        self._raise(order)
        self.assertEqual(order.reza_edbert_status, "not_needed")
        self.assertEqual(order.reza_edbert_attempts, 0,
                         "a correct order must not consume retries")

    def test_partial_survives_a_failure_before_the_retry(self):
        """Regression: _reza_mark_done used to read `partial` off the CURRENT
        status, and any failure between the create-path mark and a later
        successful resume overwrites both status and note -- so the skipped-line
        list was lost and the order was recorded as a clean success while Edbert
        was only part-supplying it."""
        unmapped = self.env["product.product"].create({
            "name": "TEST unmapped", "type": "consu", "is_storable": True,
            "standard_price": 5.0, "list_price": 10.0, "external_api_id": 0})
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [
                (0, 0, {"product_id": self.product.id, "product_uom_qty": 2.0}),
                (0, 0, {"product_id": unmapped.id, "product_uom_qty": 1.0}),
            ],
        })
        order.action_confirm()
        purchase = self._draft_purchase(order, qty=2.0)   # one line only
        order._reza_mark("failed", "the push died", purchase)   # wipes the note

        got = self._raise(order)
        self.assertTrue(got)
        self.assertEqual(order.reza_edbert_status, "partial",
                         "one sale line is not on the purchase order, so this is "
                         "NOT a clean success")
        self.assertTrue(order.reza_edbert_note,
                        "the skipped line must be named, or nobody knows it is short")

    # ------------------------------------------------------------ idempotency
    def test_it_never_raises_a_second_purchase_order(self):
        order = self._order()
        order.action_confirm()
        first = self._raise(order)
        again = self._raise(order)
        self.assertTrue(first)
        self.assertEqual(again, first,
                         "the second call must return the SAME purchase order")
        self.assertEqual(
            self.env["purchase.order"].search_count(
                [("origin", "=", order.name), ("partner_id", "=", self.vendor.id)]), 1)

    def test_a_draft_link_is_finished_not_abandoned(self):
        """Regression: an order linked to a DRAFT purchase order used to return
        False for ever while still matching the cron domain, and enough of them
        filled the batch limit and starved every order behind them."""
        order = self._order()
        order.action_confirm()
        purchase = self._draft_purchase(order)

        got = self._raise(order)
        self.assertEqual(got, purchase, "the draft link must be finished, not ignored")
        self.assertEqual(purchase.state, "purchase")
        self.assertEqual(order.reza_edbert_status, "raised")

    # ------------------------------------------------- the duplicate-order trap
    def test_an_existing_wholesale_order_is_adopted_not_duplicated(self):
        """`d3_external_api` writes external_api_sale with no commit behind it,
        so a failure after the remote create loses the link while the wholesale
        order survives, confirmed. The retry must find it and re-stamp it, not
        create a second one."""
        order = self._order()
        order.action_confirm()
        purchase = self._draft_purchase(order)        # the rollback shape
        self.assertFalse(purchase.external_api_sale)

        # line_count must MATCH the one line _draft_purchase built, or the
        # blocker-4 guard correctly refuses it and this test is asserting the
        # opposite of test_a_partial_remote_line_set_is_refused_not_adopted.
        self._raise(order, remote={"id": 4242, "name": "EBH000009999",
                                   "state": "sale", "line_count": 1})
        self.assertEqual(purchase.external_api_sale, 4242,
                         "the existing wholesale order must be adopted")
        self.assertEqual(purchase.state, "purchase")

    def test_a_half_built_wholesale_order_stops_rather_than_confirming_empty(self):
        """Vendor recovery (`confirm_external_api_sale`) only re-confirms -- it
        never creates lines. Adopting a remote order that has none would confirm
        an EMPTY wholesale order, which is worse than a duplicate because it is
        silent."""
        order = self._order()
        order.action_confirm()
        purchase = self._draft_purchase(order)

        got = self._raise(order, remote={"id": 4243, "name": "EBH000009998",
                                         "state": "draft", "line_count": 0})
        self.assertFalse(got, "a half-built remote order must stop the run")
        self.assertEqual(purchase.state, "draft", "it must NOT have been confirmed")
        self.assertEqual(order.reza_edbert_status, "failed")
        self.assertIn("0 line", order.reza_edbert_note or "")
        self.assertEqual(order.reza_edbert_attempts, 1,
                         "it must bump, or it matches the cron domain for ever and "
                         "re-reads the wholesale database every ten minutes")

    def test_a_sent_purchase_order_is_finished_not_recorded_as_raised(self):
        """Only `purchase` and `done` mean the push happened. Recording `sent`
        or `to approve` as raised would be the same silent-success fault as
        marking an unconfirmed order raised -- it drops out of the cron domain
        and nobody is told."""
        order = self._order()
        order.action_confirm()
        purchase = self._draft_purchase(order)
        purchase.write({"state": "sent"})            # RFQ sent, not confirmed

        got = self._raise(order)
        self.assertEqual(got, purchase, "a sent order must be finished, not recorded")
        self.assertEqual(purchase.state, "purchase")
        self.assertEqual(order.reza_edbert_status, "raised")

    # -------------------------------------------------- failure is not success
    def test_an_unconfirmed_purchase_order_is_marked_failed_not_raised(self):
        """Two-step approval leaves it at `to approve`. Recording that as
        `raised` would hide the note (the banner only shows it on `failed`) and
        drop the order out of the cron domain for good."""
        order = self._order()
        order.action_confirm()
        Purchase = type(self.env["purchase.order"])
        with patch.object(type(order), "_reza_edbert_costs",
                          return_value={105811: 3.3610}), \
                patch.object(type(order), "_reza_find_remote_sale", return_value=None), \
                patch.object(Purchase, "button_confirm", return_value=True):
            got = order._reza_raise_edbert_purchase()      # state stays draft
        self.assertFalse(got)
        self.assertEqual(order.reza_edbert_status, "failed")
        self.assertIn("not confirmed", order.reza_edbert_note or "")
        self.assertGreaterEqual(order.reza_edbert_attempts, 1)

    # -------------------------------------------------------- the right company
    def test_a_company_without_credentials_refuses_rather_than_using_a_parent(self):
        """Raising a brand's order on its parent would receive the goods into
        the parent's warehouse, while the customer delivery picks from the
        brand's -- so it could never reserve them."""
        self.company.sudo().write({"external_api_url": False, "external_api_db": False})
        order = self._order()
        order.action_confirm()
        got = self._raise(order)
        self.assertFalse(got)
        self.assertEqual(order.reza_edbert_status, "pending",
                         "a configuration gap must stay queued, not be marked failed")
        self.assertEqual(order.reza_edbert_attempts, 0,
                         "a configuration gap must not burn a retry -- only the root "
                         "company carries credentials today, so every brand order "
                         "would reach the cap in fifty minutes and be abandoned")
        self.assertIn("warehouse", order.reza_edbert_note or "")
        self.assertFalse(order.reza_edbert_purchase_id)

    # ------------------------------------------------------------- the cron
    def test_the_cron_picks_pending_and_retryable_failures_only(self):
        pending = self._order()
        pending.action_confirm()

        retryable = self._order()
        retryable.action_confirm()
        retryable.sudo().write({"reza_edbert_status": "failed",
                                "reza_edbert_attempts": MAX_ATTEMPTS - 1})

        exhausted = self._order()
        exhausted.action_confirm()
        exhausted.sudo().write({"reza_edbert_status": "failed",
                                "reza_edbert_attempts": MAX_ATTEMPTS})

        done = self._order()
        done.action_confirm()
        done.sudo().write({"reza_edbert_status": "raised"})

        seen = []
        with patch.object(type(pending), "_reza_raise_edbert_purchase", autospec=True,
                          side_effect=lambda rec: seen.append(rec.id)):
            self.env["sale.order"]._reza_cron_raise_edbert_purchases(limit=200)

        self.assertIn(pending.id, seen, "a pending order must be picked up")
        self.assertIn(retryable.id, seen, "a failure under the cap must be retried")
        self.assertNotIn(exhausted.id, seen,
                         "a failure at the cap must stop, or it starves the queue")
        self.assertNotIn(done.id, seen, "a raised order must not be touched again")

    def test_a_confirmed_purchase_order_with_no_stamp_is_not_called_raised(self):
        """`d3_external_api` stamps external_api_sale immediately after it
        creates the remote order, and a failure after that rolls the local
        state back to draft too -- so a CONFIRMED order carrying no stamp can
        only mean the push never ran. Confirming again would not re-run it,
        because core's button_confirm skips a confirmed order."""
        order = self._order()
        order.action_confirm()
        purchase = self._draft_purchase(order)
        purchase.write({"state": "purchase"})          # confirmed, never pushed
        self.assertFalse(purchase.external_api_sale)

        got = self._raise(order)
        self.assertFalse(got)
        self.assertEqual(order.reza_edbert_status, "failed")
        self.assertIn("never sent", order.reza_edbert_note or "")
        self.assertEqual(order.reza_edbert_attempts, 1)

    def test_an_order_waiting_for_approval_is_not_called_raised(self):
        """Two-step approval. `to approve` is not confirmed and not pushed, and
        core's button_confirm acts on draft and sent only, so it must be
        reported rather than recorded as a success or retried pointlessly."""
        order = self._order()
        order.action_confirm()
        purchase = self._draft_purchase(order)
        purchase.write({"state": "to approve"})

        got = self._raise(order)
        self.assertFalse(got)
        self.assertEqual(purchase.state, "to approve", "it must not have been touched")
        self.assertEqual(order.reza_edbert_status, "failed")
        self.assertIn("approval", order.reza_edbert_note or "")
        self.assertEqual(order.reza_edbert_attempts, 1)

    def test_a_partial_remote_line_set_is_refused_not_adopted(self):
        """The vendor creates the remote order EMPTY, stamps it, then creates
        the remote lines ONE call at a time -- each landing on the far side
        while the local transaction can still roll back. A partial line set is
        therefore a WIDER window than an empty one, and adopting it would
        under-supply the customer silently. `!=` not `<`, so extra lines are
        refused too."""
        order = self._order()
        order.action_confirm()
        purchase = self._draft_purchase(order)         # exactly one line

        got = self._raise(order, remote={"id": 4244, "name": "EBH000009997",
                                         "state": "draft", "line_count": 2})
        self.assertFalse(got, "a line count that does not match must stop the run")
        self.assertEqual(purchase.state, "draft", "it must NOT have been confirmed")
        self.assertFalse(purchase.external_api_sale, "it must NOT have been adopted")
        self.assertEqual(order.reza_edbert_status, "failed")
        self.assertIn("not the 1 expected", order.reza_edbert_note or "")
        self.assertEqual(order.reza_edbert_attempts, 1)

    def test_the_cron_skips_an_order_whose_company_has_no_credentials(self):
        """It can never be raised, so selecting it would waste a slot in every
        batch for ever -- the queue starvation the draft-link fix removed,
        arriving by another route."""
        order = self._order()
        order.action_confirm()
        self.company.sudo().write({"external_api_url": False, "external_api_db": False})

        seen = []
        with patch.object(type(order), "_reza_raise_edbert_purchase", autospec=True,
                          side_effect=lambda rec: seen.append(rec.id)):
            self.env["sale.order"]._reza_cron_raise_edbert_purchases(limit=200)
        self.assertNotIn(order.id, seen)
        self.assertEqual(order.reza_edbert_status, "pending",
                         "it must stay queued so it returns when the settings land")

    def test_a_blocked_order_does_not_consume_a_batch_slot(self):
        """The credential test has to be a DOMAIN leaf, not a filter applied
        after `limit`. A blocked order never changes status, so it is selected
        on every pass for ever; filtering afterwards lets the oldest blocked
        orders fill the batch and the queue does no work at all.

        `test_the_cron_skips_an_order_whose_company_has_no_credentials` cannot
        see this -- it proves the blocked order is not PROCESSED, which is a
        different property from whether it consumes a slot.
        """
        # Must be a company the test user actually holds, or create() raises
        # "Access to unauthorized or invalid companies".
        other = (self.env.user.company_ids - self.company)[:1]
        if not other:
            self.skipTest("needs a second allowed company to construct head-of-line "
                          "blocking")
        other.sudo().write({"external_api_url": False, "external_api_db": False})

        blocked = self._order(company=other)         # lower id, and unraisable
        blocked.action_confirm()
        processable = self._order()                  # higher id, and raisable
        processable.action_confirm()

        seen = []
        with patch.object(type(blocked), "_reza_raise_edbert_purchase", autospec=True,
                          side_effect=lambda rec: seen.append(rec.id)):
            self.env["sale.order"]._reza_cron_raise_edbert_purchases(limit=1)

        self.assertNotIn(blocked.id, seen)
        self.assertIn(processable.id, seen,
                      "the blocked order ahead of it must not have taken the slot")

    # -------------------------------------------------------- the button works
    def test_the_view_calls_the_public_button_target(self):
        """A private method installs and validates fine, then raises AccessError
        on every click (`check_method_name`, regex `^(_.*|init)$`). Read the real
        arch -- asserting on a hardcoded string here would pass for ever."""
        arch = self.env["sale.order"].get_view(view_type="form")["arch"]
        self.assertIn("action_reza_raise_edbert_purchase", arch,
                      "the button is missing from the sale order form")
        self.assertNotIn('name="_reza_raise_edbert_purchase"', arch,
                         "the button must not call the private worker directly")
        self.assertTrue(hasattr(self.env["sale.order"],
                                "action_reza_raise_edbert_purchase"))
