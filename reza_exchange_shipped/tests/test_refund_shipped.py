# -*- coding: utf-8 -*-
"""Refund (shipped) and the customer-refund check.

Stripe and PayPal are never called: `_provider_refunds` is patched to return
what the provider would say, and the Odoo-sent Stripe refund is patched at
`_send_refund_request`.
"""
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .test_exchange_shipped import TestExchangeShipped

PARAM_AUTO = "reza_exchange_shipped.refund_auto"
PARAM_USER = "reza_exchange_shipped.refund_user_id"


@tagged("post_install", "-at_install")
class TestRefundShipped(TestExchangeShipped):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.accounts = new_test_user(
            cls.env, login="reza_uts_accounts", groups="account.group_account_invoice",
            company_id=cls.company.id, company_ids=[cls.company.id])
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_USER, cls.accounts.id)
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_AUTO, False)
        Provider = cls.env["payment.provider"].sudo()
        cls.stripe = Provider.search([("code", "=", "stripe"), ("company_id", "=", cls.company.id)],
                                     limit=1)
        cls.paypal = Provider.search([("code", "=", "paypal"), ("company_id", "=", cls.company.id)],
                                     limit=1)
        cls.card = cls.env.ref("payment.payment_method_card")
        # The April copy's bank journals carry no outstanding account, so no
        # payment can be registered. Production's do (set 2026-11-06).
        outstanding = cls.env["account.account"].search([
            ("company_ids", "in", cls.company.id), ("account_type", "=", "asset_current"),
            ("deprecated", "=", False)], limit=1)
        banks = cls.env["account.journal"].search(
            [("type", "in", ("bank", "cash")), ("company_id", "=", cls.company.id)])
        (banks.inbound_payment_method_line_ids | banks.outbound_payment_method_line_ids).filtered(
            lambda l: not l.payment_account_id).payment_account_id = outstanding
        if not cls.stripe.journal_id:
            cls.stripe.journal_id = banks.filtered(lambda j: j.type == "bank")[:1]

    # ----------------------------------------------------------------- helpers
    def _stripe_tx(self, order, amount=None, reference="pi_TEST123", provider=None):
        tx = self.env["payment.transaction"].sudo().create({
            "provider_id": (provider or self.stripe).id,
            "payment_method_id": self.card.id,
            "reference": "UTS-%s-%s" % (order.name, reference),
            "amount": amount or order.amount_total,
            "currency_id": order.currency_id.id,
            "partner_id": self.partner.id,
            "provider_reference": reference,
            "sale_order_ids": [Command.set(order.ids)],
        })
        tx._set_done()
        return tx

    def _refund_it(self, order, qtys, user=None, shipping=False, reason="Change of mind"):
        wizard = self.env["reza.refund.shipped.wizard"].with_user(user or self.user) \
            .with_context(default_order_id=order.id).create(
                {"refund_shipping": shipping, "reason": reason})
        for wl in wizard.line_ids:
            wl.qty_to_return = qtys.get(wl.product_id, 0.0)
        return wizard.action_apply()

    def _rows(self, order):
        return self.env["reza.customer.refund"].sudo().search([("sale_order_id", "=", order.id)])

    def _provider_says(self, refunds):
        """Patch the provider read for every row."""
        self.patch(type(self.env["reza.customer.refund"]), "_provider_refunds",
                   lambda self: [dict(r) for r in refunds])

    def _age(self, rows, days):
        self.env.cr.execute("UPDATE reza_customer_refund SET create_date = %s WHERE id IN %s",
                            (fields.Datetime.now() - timedelta(days=days), tuple(rows.ids)))
        rows.invalidate_recordset()

    # --------------------------------------------------- the button, money off
    def test_refund_returns_credits_and_tasks_accounts(self):
        order, __, purchase = self._shipped()
        self._stripe_tx(order)
        self._fake()
        before = self._onhand(self.nobbies)
        self._refund_it(order, {self.nobbies: 1})
        line = self._line(order, self.nobbies)
        self.assertEqual(line.qty_delivered, 1, "the customer return did not land")
        self.assertEqual(line.product_uom_qty, 1, "ordered quantity not lowered: order would read To invoice")
        self.assertEqual(self._onhand(self.nobbies), before + 1)
        self.assertNotEqual(order.invoice_status, "to invoice",
                            "Create Invoice would bill the customer again")
        refund = self._refund(order)
        self.assertEqual(refund.state, "posted")
        self.assertAlmostEqual(refund.amount_total, 24.99, msg="credit is not the GST-inclusive price paid")
        row = self._rows(order)
        self.assertEqual(len(row), 1)
        self.assertEqual(row.state, "waiting")
        self.assertAlmostEqual(row.amount, 24.99)
        self.assertEqual(row.provider_reference, "pi_TEST123")
        self.assertEqual(row.activity_id.user_id, self.accounts, "the task did not go to Accounts")
        self.assertIn("pi_TEST123", row.activity_id.note)
        self.assertIn("$", row.activity_id.summary)
        edbert = order.reza_edbert_return_ids
        self.assertEqual(len(edbert), 1, "the returned item is not going back to Edbert")
        self.assertEqual(edbert.qty, 1)
        self.assertEqual(edbert.purchase_id, purchase)

    def test_auto_refund_is_off_by_default(self):
        self.env["ir.config_parameter"].sudo().search([("key", "=", PARAM_AUTO)]).unlink()
        # A refundable Stripe payment, so the setting is the ONLY thing that
        # stops Odoo sending money (same fixture as the "on" test).
        order, invoice, __ = self._shipped(paid=False)
        tx = self._stripe_tx(order)
        tx.invoice_ids = [Command.set(invoice.ids)]
        tx._create_payment()
        self.assertGreaterEqual(tx.payment_id.amount_available_for_refund, 24.99)
        self._fake()
        with patch.object(type(self.env["payment.transaction"]), "_send_refund_request",
                          autospec=True) as send:
            self._refund_it(order, {self.nobbies: 1})
        send.assert_not_called()
        self.assertEqual(self._rows(order).state, "waiting")

    def test_shipping_not_refunded_unless_ticked(self):
        carrier = self._carrier()
        order, __, __ = self._shipped(carrier=carrier)
        self._fake()
        self._refund_it(order, {self.nobbies: 1, self.thongs: 1})
        refund = self._refund(order)
        self.assertFalse(refund.invoice_line_ids.filtered(lambda l: l.sale_line_ids.is_delivery),
                         "shipping refunded without the box ticked")
        self.assertAlmostEqual(refund.amount_total, 24.99 + 22.99)

    def test_shipping_refunded_when_ticked(self):
        carrier = self._carrier()
        order, __, __ = self._shipped(carrier=carrier)
        self._fake()
        self._refund_it(order, {self.nobbies: 2, self.thongs: 1}, shipping=True)
        refund = self._refund(order)
        ship = refund.invoice_line_ids.filtered(lambda l: l.sale_line_ids.is_delivery)
        self.assertEqual(len(ship), 1, "shipping not on the credit note")
        self.assertAlmostEqual(refund.amount_total, 2 * 24.99 + 22.99 + 12.50)
        self.assertEqual(order.order_line.filtered("is_delivery").product_uom_qty, 0)

    def test_shipping_ticked_with_none_is_refused(self):
        order, __, __ = self._shipped()
        self._fake()
        with self.assertRaises(UserError) as cm:
            self._refund_it(order, {self.nobbies: 1}, shipping=True)
        self.assertIn("no invoiced shipping", str(cm.exception))

    def test_more_than_delivered_is_refused_for_refund(self):
        order, __, __ = self._shipped()
        with self.assertRaises(UserError) as cm:
            self._refund_it(order, {self.nobbies: 3})
        self.assertIn("only 2.0 was delivered", str(cm.exception))

    def test_refund_needs_inventory_rights(self):
        order, __, __ = self._shipped()
        weak = new_test_user(
            self.env, login="reza_uts_refund_weak",
            groups="sales_team.group_sale_salesman_all_leads,account.group_account_invoice",
            company_id=self.company.id, company_ids=[self.company.id])
        with self.assertRaises(AccessError) as cm:
            self._refund_it(order, {self.nobbies: 1}, user=weak)
        self.assertIn("Refund (shipped) needs", str(cm.exception))

    def test_bank_transfer_order_gets_a_task_without_provider(self):
        order, __, __ = self._shipped()
        self._fake()
        self._refund_it(order, {self.thongs: 1})
        row = self._rows(order)
        self.assertFalse(row.provider_code)
        self.assertIn("no online payment", row.activity_id.note)

    # ------------------------------------------------------------ daily check
    def test_check_settles_when_provider_refunded(self):
        order, __, __ = self._shipped()
        self._stripe_tx(order)
        self._fake()
        self._refund_it(order, {self.nobbies: 1})
        row = self._rows(order)
        refund = row.credit_note_id
        self.assertFalse(refund.currency_id.is_zero(refund.amount_residual),
                         "fixture: the paid invoice should leave the credit note open")
        self._provider_says([{"id": "re_1", "amount": 24.99, "date": fields.Date.today()}])
        self.env["reza.customer.refund"]._cron_check()
        self.assertEqual(row.state, "done")
        self.assertEqual(row.provider_refund_ids, "re_1")
        self.assertTrue(refund.currency_id.is_zero(refund.amount_residual),
                        "the refund was not recorded on the credit note")
        self.assertFalse(row.activity_id.exists(), "the Accounts task is still open")

    def test_check_flags_a_different_amount(self):
        """MJ00225: the tax-excluded figure was refunded."""
        order, __, __ = self._shipped()
        self._stripe_tx(order)
        self._fake()
        self._refund_it(order, {self.nobbies: 1})
        row = self._rows(order)
        self._provider_says([{"id": "re_1", "amount": 22.72, "date": fields.Date.today()}])
        self.env["reza.customer.refund"]._cron_check()
        self.assertEqual(row.state, "mismatch")
        self.assertIn("22.72", row.note)
        self.assertFalse(row.credit_note_id.currency_id.is_zero(row.credit_note_id.amount_residual),
                         "a wrong refund was recorded as the right one")

    def test_check_flags_late_after_three_days(self):
        """RKS00086: nothing refunded, credit note looked Paid."""
        order, __, __ = self._shipped()
        self._stripe_tx(order)
        self._fake()
        self._refund_it(order, {self.nobbies: 1})
        row = self._rows(order)
        self._provider_says([])
        self._age(row, 2)
        self.env["reza.customer.refund"]._cron_check()
        self.assertEqual(row.state, "waiting", "flagged late too early")
        self._age(row, 4)
        self.env["reza.customer.refund"]._cron_check()
        self.assertEqual(row.state, "late")
        self.assertIn("NOT been refunded", order.message_ids[0].body)

    def test_one_refund_is_never_counted_twice(self):
        order, __, __ = self._shipped()
        self._stripe_tx(order)
        self._fake()
        self._refund_it(order, {self.nobbies: 1})
        self._refund_it(order, {self.nobbies: 1})
        rows = self._rows(order).sorted("id")
        self.assertEqual(len(rows), 2)
        self._provider_says([{"id": "re_1", "amount": 24.99, "date": fields.Date.today()}])
        self.env["reza.customer.refund"]._cron_check()
        self.assertEqual(rows.mapped("state"), ["done", "waiting"],
                         "one Stripe refund settled two credit notes")

    def test_no_double_payment_when_accounts_already_registered(self):
        order, __, __ = self._shipped()
        self._stripe_tx(order)
        self._fake()
        self._refund_it(order, {self.nobbies: 1})
        row = self._rows(order)
        cn = row.credit_note_id
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=cn.ids).create({}).action_create_payments()
        payments_before = cn.matched_payment_ids
        self._provider_says([{"id": "re_1", "amount": 24.99, "date": fields.Date.today()}])
        self.env["reza.customer.refund"]._cron_check()
        self.assertEqual(row.state, "done")
        self.assertEqual(cn.matched_payment_ids, payments_before, "a second payment was registered")
        self.assertFalse(row.note, "the check tried to record a second payment: %s" % row.note)
        self.assertFalse(row.activity_id.exists(), "the Accounts task is still open")

    def test_registered_in_odoo_but_not_in_stripe_stays_open(self):
        """The RKS00086 trap: Odoo says Paid, the provider says otherwise."""
        order, __, __ = self._shipped()
        self._stripe_tx(order)
        self._fake()
        self._refund_it(order, {self.nobbies: 1})
        row = self._rows(order)
        cn = row.credit_note_id
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=cn.ids).create({}).action_create_payments()
        self._provider_says([])
        self.env["reza.customer.refund"]._cron_check()
        self.assertNotEqual(row.state, "done", "trusted Odoo's Paid over the provider")

    def test_refund_found_but_recording_fails_keeps_task(self):
        order, __, __ = self._shipped()
        self._stripe_tx(order)
        self._fake()
        self._refund_it(order, {self.nobbies: 1})
        row = self._rows(order)
        self._provider_says([{"id": "re_1", "amount": 24.99, "date": fields.Date.today()}])

        def boom(self, amount, date):
            raise UserError("No outstanding account could be found to make the payment")
        self.patch(type(self.env["reza.customer.refund"]), "_record_payment", boom)
        self.env["reza.customer.refund"]._cron_check()
        self.assertEqual(row.state, "done", "the customer WAS refunded")
        self.assertIn("Register Payment", row.note)
        self.assertTrue(row.activity_id.exists(), "task closed although nothing was recorded")

    def test_provider_read_error_is_noted_not_raised(self):
        from odoo.addons.reza_exchange_shipped.models.customer_refund import ProviderReadError
        order, __, __ = self._shipped()
        self._stripe_tx(order)
        self._fake()
        self._refund_it(order, {self.nobbies: 1})
        row = self._rows(order)

        def boom(self):
            raise ProviderReadError("HTTP 500")
        self.patch(type(self.env["reza.customer.refund"]), "_provider_refunds", boom)
        self.env["reza.customer.refund"]._cron_check()
        self.assertEqual(row.state, "waiting")
        self.assertIn("HTTP 500", row.note)

    def test_check_now_needs_invoicing_rights(self):
        order, __, __ = self._shipped()
        self._fake()
        self._refund_it(order, {self.nobbies: 1})
        row = self._rows(order)
        plain = new_test_user(self.env, login="reza_uts_refund_plain",
                              groups="sales_team.group_sale_salesman_all_leads",
                              company_id=self.company.id, company_ids=[self.company.id])
        with self.assertRaises(AccessError) as cm:
            row.with_user(plain).action_check()
        self.assertIn("Only Invoicing users", str(cm.exception))

    def test_cron_check_runs_as_superuser_without_the_group(self):
        plain = new_test_user(self.env, login="reza_uts_refund_cronless",
                              groups="base.group_user",
                              company_id=self.company.id, company_ids=[self.company.id])
        self._provider_says([])
        self.assertTrue(self.env["reza.customer.refund"].with_env(
            self.env(user=plain, su=True))._cron_check())
        with self.assertRaises(AccessError):
            self.env["reza.customer.refund"].with_user(plain)._cron_check()

    # ------------------------------------------------------------- money on
    def _auto_on_order(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_AUTO, True)
        order, invoice, __ = self._shipped(paid=False)
        tx = self._stripe_tx(order)
        tx.invoice_ids = [Command.set(invoice.ids)]
        tx._create_payment()
        self._fake()
        return order

    def _fake_send(self, sent, fail=False):
        def fake_send(tx, amount_to_refund=None):
            if fail:
                raise RuntimeError("Stripe said card_declined")
            sent.append(amount_to_refund)
            return tx._create_child_transaction(amount_to_refund, is_refund=True)
        return patch.object(type(self.env["payment.transaction"]), "_send_refund_request", fake_send)

    def test_auto_refund_on_queues_then_cron_sends(self):
        order = self._auto_on_order()
        sent = []
        with self._fake_send(sent):
            self._refund_it(order, {self.nobbies: 1})
            row = self._rows(order)
            self.assertEqual(sent, [], "money sent inside the wizard's uncommitted request")
            self.assertEqual(row.state, "queued")
            self.assertFalse(row.activity_id, "a task was opened for a refund Odoo will send")
            self.env["reza.customer.refund"]._cron_send()
        self.assertEqual(sent, [24.99])
        self.assertEqual(row.state, "sent")
        self.assertTrue(row.odoo_refund_tx_id)

    def test_a_sending_row_is_never_sent_again(self):
        """A crash after Stripe was called leaves the row 'sending'. It must
        not go out twice."""
        order = self._auto_on_order()
        sent = []
        with self._fake_send(sent):
            self._refund_it(order, {self.nobbies: 1})
            row = self._rows(order)
            row.state = "sending"
            self.env["reza.customer.refund"]._cron_send()
            self.env["reza.customer.refund"]._cron_send()
        self.assertEqual(sent, [], "a refund that may already be paid was sent again")

    def test_failed_send_falls_back_to_a_task(self):
        order = self._auto_on_order()
        with self._fake_send([], fail=True):
            self._refund_it(order, {self.nobbies: 1})
            self.env["reza.customer.refund"]._cron_send()
        row = self._rows(order)
        self.assertEqual(row.state, "waiting")
        self.assertIn("card_declined", row.note)
        self.assertEqual(row.activity_id.user_id, self.accounts)

    def test_auto_refund_on_paypal_still_tasks_accounts(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_AUTO, True)
        order, __, __ = self._shipped()
        self._stripe_tx(order, reference="8PAYPALCAPTURE", provider=self.paypal)
        self._fake()
        with patch.object(type(self.env["payment.transaction"]), "_send_refund_request",
                          autospec=True) as send:
            self._refund_it(order, {self.nobbies: 1})
        send.assert_not_called()
        row = self._rows(order)
        self.assertEqual(row.provider_code, "paypal")
        self.assertEqual(row.activity_id.user_id, self.accounts)
        self.assertIn("PayPal, transaction 8PAYPALCAPTURE", row.activity_id.note)


# The exchange tests are inherited for their fixtures only; run them once, in
# their own class.
for _name in dir(TestExchangeShipped):
    if _name.startswith("test_") and _name not in TestRefundShipped.__dict__:
        setattr(TestRefundShipped, _name, None)
