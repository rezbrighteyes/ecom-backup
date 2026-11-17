# -*- coding: utf-8 -*-
"""Make sure the customer actually gets their money back.

Why this exists (audit, 2026-11-16): a credit note in Odoo sends no money. The
refund is done by hand in Stripe or PayPal, and nothing checks that it was.
RKS00086 read "Paid" for 14 days while PayPal still held the customer's
$114.95; MJ00225 was refunded the tax-EXCLUDED figure, $21.82 short; MJ00842
and MJ00178 were never refunded at all.

One row per credit note that owes the customer money. The row knows which
Stripe or PayPal payment the money came in on, and a daily cron reads that
payment's refunds straight from the provider:

* a refund for the right amount appears -> it is recorded on the credit note
  as a payment (so the credit note reads Paid for a real reason), the
  Accounts task is closed, the row is Done;
* a refund for a different amount appears -> "Amount differs", with both
  figures, and nothing is recorded;
* nothing appears after LATE_DAYS -> "Not refunded", said once on the order.

Whether Odoo SENDS the refund itself is a setting (Sales > Settings, "Send
refunds through Odoo"), OFF by default. Off: Accounts gets a task with the
amount, the provider and the transaction, and does the refund in Stripe or
PayPal. On: a Stripe refund is sent from Odoo the moment the credit note is
made. PayPal is always by hand: Odoo's PayPal integration cannot refund
(`support_refund = none`).

The provider is only READ here, except for that one send. A read failure is
recorded on the row and retried the next day; it never blocks anything.
"""
import logging
from datetime import datetime, timedelta, timezone

import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import format_amount

_logger = logging.getLogger(__name__)

LATE_DAYS = 3
TOLERANCE = 0.01          # dollars: a refund "matches" within one cent
TIMEOUT = 30              # seconds, every provider call
PARAM_AUTO = "reza_exchange_shipped.refund_auto"
PARAM_USER = "reza_exchange_shipped.refund_user_id"
PARAM_ALERT = "reza_exchange_shipped.refund_alert_emails"
DEFAULT_REFUND_LOGIN = "accounts@brighteyes.com.au"
# Who else hears about a refund that went wrong (late or a different amount).
DEFAULT_ALERT_EMAILS = "reza@brighteyes.com.au,luke@brighteyes.com.au"


class ProviderReadError(Exception):
    """The provider could not tell us about this payment."""


class RezaCustomerRefund(models.Model):
    _name = "reza.customer.refund"
    _description = "Customer refund to check"
    _order = "id desc"

    name = fields.Char(required=True, readonly=True, copy=False, default="/")
    sale_order_id = fields.Many2one("sale.order", required=True, readonly=True, index=True,
                                    ondelete="restrict")
    credit_note_id = fields.Many2one("account.move", required=True, readonly=True, index=True,
                                     ondelete="restrict")
    company_id = fields.Many2one(related="credit_note_id.company_id", store=True)
    currency_id = fields.Many2one(related="credit_note_id.currency_id", store=True)
    amount = fields.Monetary("To Refund", required=True, readonly=True,
                             help="What the customer must get back, GST included.")
    transaction_id = fields.Many2one(
        "payment.transaction", string="Paid With", readonly=True,
        help="The online payment the money came in on. Empty for a bank transfer or cash.")
    provider_code = fields.Char(readonly=True)
    provider_reference = fields.Char("Provider Reference", readonly=True)
    state = fields.Selection([
        ("waiting", "Waiting for refund"),
        ("queued", "Queued for Odoo to send"),
        ("sending", "Being sent by Odoo"),
        ("sent", "Sent by Odoo"),
        ("mismatch", "Amount differs"),
        ("late", "Not refunded"),
        ("done", "Refunded"),
    ], default="waiting", required=True, readonly=True, index=True)
    refunded_amount = fields.Monetary("Refunded", readonly=True)
    refund_date = fields.Date(readonly=True)
    provider_refund_ids = fields.Char(
        "Provider Refunds", readonly=True,
        help="The provider's ids of the refunds counted against this row, comma separated. "
        "A refund is never counted against two rows.")
    odoo_refund_tx_id = fields.Many2one("payment.transaction", string="Odoo Refund",
                                        readonly=True)
    activity_id = fields.Many2one("mail.activity", readonly=True, ondelete="set null")
    note = fields.Char(readonly=True)
    last_check = fields.Datetime(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                order = self.env["sale.order"].browse(vals["sale_order_id"])
                n = self.search_count([("sale_order_id", "=", order.id)]) + 1
                vals["name"] = "%s-RF%d" % (order.name, n)
        return super().create(vals_list)

    # --------------------------------------------------------------- settings
    @api.model
    def _auto_refund_enabled(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(PARAM_AUTO)
        # get_param returns False for a missing key, and a string otherwise.
        return raw not in (None, False, "", "False", "false", "0")

    @api.model
    def _refund_user(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(PARAM_USER)
        # Test the raw value BEFORE int(): int(False) is 0, not "unset".
        if raw not in (None, False, ""):
            try:
                user = self.env["res.users"].sudo().browse(int(raw)).exists()
            except (TypeError, ValueError):
                user = self.env["res.users"]
            if user and user.active:
                return user
        user = self.env["res.users"].sudo().search([("login", "=", DEFAULT_REFUND_LOGIN)], limit=1)
        return user or self.env.user

    # ------------------------------------------------------------- start one
    @api.model
    def _start(self, order, credit_notes):
        """One row per posted credit note that owes money. Called by the
        Refund (shipped) wizard, inside its transaction."""
        rows = self.browse()
        tx = self._source_transaction(order)
        for cn in credit_notes.filtered(lambda m: m.state == "posted"):
            if cn.currency_id.is_zero(cn.amount_total):
                continue
            row = self.sudo().create({
                "sale_order_id": order.id,
                "credit_note_id": cn.id,
                "amount": cn.amount_total,
                "transaction_id": tx.id,
                "provider_code": tx.provider_code if tx else False,
                "provider_reference": tx.provider_reference if tx else False,
            })
            if not row._queue_send():
                row._open_task()
            rows |= row
        if rows.filtered(lambda r: r.state == "queued"):
            self.env.ref("reza_exchange_shipped.ir_cron_reza_customer_refund_send").sudo()._trigger()
        return rows

    @api.model
    def _source_transaction(self, order):
        """The confirmed online payment for the order: the newest one that
        is not itself a refund."""
        txs = order.sudo().transaction_ids.filtered(
            lambda t: t.state == "done" and t.operation != "refund"
            and t.provider_code in ("stripe", "paypal") and t.provider_reference)
        return txs.sorted("id", reverse=True)[:1]

    def _queue_send(self):
        """Setting ON + Stripe + a refundable payment: queue the row for the
        send cron. The money is NEVER sent from inside the wizard's request:
        that request has not committed, so a later error (or a retry after a
        serialization failure) would roll back the record of a refund Stripe
        had already paid out -- or pay it twice."""
        self.ensure_one()
        if not self._auto_refund_enabled() or self.provider_code != "stripe":
            return False
        payment = self.transaction_id.sudo().payment_id
        if not payment or payment.amount_available_for_refund + TOLERANCE < self.amount:
            self.note = _("Odoo could not send this refund: the Stripe payment has no room for it.")
            return False
        self.state = "queued"
        return True

    @api.model
    def _cron_send(self, limit=50):
        """Send queued Stripe refunds, one per transaction.

        The row is written "sending" and COMMITTED before Stripe is called,
        and only a "queued" row is ever sent. So whatever happens after the
        call -- a crash, a timeout, a failed commit -- the row is never sent
        a second time; the daily check finds the refund in Stripe and settles
        it, or flags it late."""
        if not self.env.su and not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("Only Invoicing users can send refunds."))
        rows = self.sudo().search([("state", "=", "queued")], order="id asc", limit=limit)
        for row in rows:
            row.state = "sending"
            self.env.cr.commit()
            try:
                with self.env.cr.savepoint():
                    tx = row.transaction_id.sudo()
                    refund_tx = tx.with_context(payment_backend_action=True)._send_refund_request(
                        amount_to_refund=row.amount)
                row.write({"state": "sent", "odoo_refund_tx_id": refund_tx.id,
                           "note": _("Refund sent to Stripe by Odoo.")})
                row.sale_order_id.message_post(body=_(
                    "%(cn)s: Odoo sent a refund of %(amt)s to Stripe.",
                    cn=row.credit_note_id.name, amt=row._fmt(row.amount)))
            except Exception as exc:  # noqa: BLE001
                _logger.exception("reza_exchange_shipped: Stripe refund for %s failed", row.name)
                row.write({"state": "waiting",
                           "note": _("Odoo could not send this refund: %s", str(exc)[:300])})
                row._open_task()
                row.sale_order_id.message_post(body=_(
                    "%(cn)s: Odoo could not send the refund to Stripe (%(err)s). %(task)s",
                    cn=row.credit_note_id.name, err=str(exc)[:200], task=row._task_text()))
            self.env.cr.commit()
        return True

    def _task_text(self):
        self.ensure_one()
        amount = self._fmt(self.amount)
        if self.provider_code == "stripe":
            where = _("Stripe, payment %s", self.provider_reference)
        elif self.provider_code == "paypal":
            where = _("PayPal, transaction %s", self.provider_reference)
        else:
            where = _("the way the customer paid (no online payment found in Odoo)")
        return _("Refund %(amount)s to %(customer)s in %(where)s.",
                 amount=amount, customer=self.sale_order_id.partner_id.display_name, where=where)

    def _open_task(self):
        """The task in Odoo, plus an email of our own.

        The activity's built-in "You have been assigned" notification is
        switched off (mail_activity_quick_update): it is queued behind a
        12-hour mail cron and sent from odoobot@, which the Outlook server's
        from_filter does not list. The email below is sent from the shop's
        own address, kept after sending as proof, and the queue is triggered
        at once."""
        self.ensure_one()
        user = self._refund_user()
        activity = self.credit_note_id.sudo().with_context(
            mail_activity_quick_update=True).activity_schedule(
            "mail.mail_activity_data_todo",
            date_deadline=fields.Date.context_today(self),
            summary=_("Refund %s", self._fmt(self.amount)),
            note=self._task_text(),
            user_id=user.id,
        )
        self.activity_id = activity
        self._email_staff(
            _("Refund to do: %(amt)s for %(so)s", amt=self._fmt(self.amount),
              so=self.sale_order_id.name),
            _("A customer return was credited. Please refund the customer now."),
            [user.email])

    # ------------------------------------------------------------------ check
    def action_check(self):
        """Button target ("Check now"), so public; the group is re-tested
        here because the check reads provider credentials."""
        if not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("Only Invoicing users can check refunds."))
        for row in self.filtered(lambda r: r.state not in ("done", "queued")):
            row.sudo()._check()
        return True

    @api.model
    def _cron_check(self, limit=200):
        if not self.env.su and not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("Only Invoicing users can check refunds."))
        rows = self.sudo().search([("state", "not in", ("done", "queued"))],
                                  order="id asc", limit=limit)
        for row in rows:
            try:
                with self.env.cr.savepoint():
                    row._check()
            except Exception as exc:  # noqa: BLE001 -- one bad row must not stop the rest
                _logger.exception("reza_exchange_shipped: refund check %s failed", row.name)
                row.invalidate_recordset()
                row.note = _("The check failed: %s", str(exc)[:300])
            self.env.cr.commit()
        return True

    def _check(self):
        """Never raises for a provider problem: it is noted and retried."""
        self.ensure_one()
        self.last_check = fields.Datetime.now()
        if self.provider_code not in ("stripe", "paypal"):
            return self._check_offline()
        try:
            refunds = self._provider_refunds()
        except ProviderReadError as exc:
            self.note = _("Could not read %(p)s: %(e)s", p=self.provider_code, e=str(exc)[:300])
            return self._maybe_late()
        claimed = set()
        others = self.search([("id", "!=", self.id),
                              ("provider_reference", "=", self.provider_reference)])
        for other in others:
            claimed.update(filter(None, (other.provider_refund_ids or "").split(",")))
        free = [r for r in refunds if r["id"] not in claimed]
        pick = self._pick(free)
        if pick:
            return self._settle(pick)
        if free:
            total = sum(r["amount"] for r in free)
            was = self.state
            self.write({"state": "mismatch", "refunded_amount": total, "note": _(
                "%(p)s shows %(got)s refunded, but this credit note is %(want)s. Check it, "
                "then refund the difference or correct the credit note.",
                p=self.provider_code.capitalize(), got=self._fmt(total), want=self._fmt(self.amount))})
            if was != "mismatch":
                self._email_staff(
                    _("Refund amount differs: %(so)s", so=self.sale_order_id.name),
                    self.note, self._alert_emails())
            return False
        return self._maybe_late()

    def _pick(self, free):
        """The refunds that pay this row: one refund of exactly the amount,
        or (failing that) all the unclaimed refunds together when they add up
        to it. Anything else is not a match."""
        for r in free:
            if abs(r["amount"] - self.amount) <= TOLERANCE:
                return [r]
        if len(free) > 1 and abs(sum(r["amount"] for r in free) - self.amount) <= TOLERANCE:
            return free
        return []

    def _settle(self, refunds):
        total = sum(r["amount"] for r in refunds)
        date = max(r["date"] for r in refunds)
        self.write({
            "state": "done",
            "refunded_amount": total,
            "refund_date": date,
            "provider_refund_ids": ",".join(r["id"] for r in refunds),
            "note": False,
        })
        body = _("Refund checked: %(p)s refunded %(amt)s on %(d)s for %(cn)s.",
                 p=self.provider_code.capitalize(), amt=self._fmt(total),
                 d=fields.Date.to_string(date), cn=self.credit_note_id.name)
        try:
            with self.env.cr.savepoint():
                recorded = self._record_payment(total, date)
        except Exception as exc:  # noqa: BLE001
            # The money HAS gone back; only the bookkeeping failed. Keep the
            # task open so Accounts records it by hand.
            _logger.exception("reza_exchange_shipped: recording refund %s failed", self.name)
            self.note = _("Refunded, but Odoo could not record it on the credit note: %s. "
                          "Click Register Payment on the credit note.", str(exc)[:200])
            self.sale_order_id.message_post(body=body + " " + self.note)
            return True
        self._close_task(_("%(p)s refunded %(amt)s on %(d)s.", p=self.provider_code.capitalize(),
                           amt=self._fmt(total), d=fields.Date.to_string(date)))
        if not recorded:
            body += " " + _("The credit note was already settled in Odoo, so no payment was added.")
        self.sale_order_id.message_post(body=body)
        return True

    def _record_payment(self, amount, date):
        """Settle the credit note with the refund that really happened.
        Never registers twice: only what is still open on the credit note,
        and an Odoo-sent refund's own payment is matched rather than a new
        one created."""
        cn = self.credit_note_id
        if cn.currency_id.is_zero(cn.amount_residual):
            return False
        own = self.odoo_refund_tx_id.payment_id
        if own and own.move_id:
            lines = (cn.line_ids | own.move_id.line_ids).filtered(
                lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled)
            lines.reconcile()
            return True
        vals = {"amount": min(amount, cn.amount_residual), "payment_date": date,
                "communication": _("Refund %s", self.provider_reference or cn.name)}
        journal = self.transaction_id.sudo().provider_id.journal_id
        if journal and journal.outbound_payment_method_line_ids:
            vals["journal_id"] = journal.id
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=cn.ids).create(vals)
        wizard.action_create_payments()
        return True

    def _check_offline(self):
        """Bank transfer or cash: nothing to read, so the row is done once
        Accounts has registered the refund on the credit note."""
        cn = self.credit_note_id
        if cn.currency_id.is_zero(cn.amount_residual) and cn.matched_payment_ids:
            self.write({"state": "done", "refunded_amount": self.amount,
                        "refund_date": fields.Date.context_today(self), "note": False})
            self._close_task(_("Refund registered on %s.", cn.name))
            return True
        return self._maybe_late()

    def _maybe_late(self):
        if self.state in ("waiting", "sending", "sent") and \
                fields.Datetime.now() - self.create_date > timedelta(days=LATE_DAYS):
            self.state = "late"
            text = _("%(cn)s: the customer has NOT been refunded %(amt)s after %(n)s days.",
                     cn=self.credit_note_id.name, amt=self._fmt(self.amount), n=LATE_DAYS)
            self.sale_order_id.message_post(body=text + " " + self._task_text())
            self._email_staff(
                _("NOT refunded after %(n)s days: %(so)s", n=LATE_DAYS, so=self.sale_order_id.name),
                text, self._alert_emails())
        return False

    # ----------------------------------------------------------------- emails
    def _alert_emails(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(PARAM_ALERT)
        extra = DEFAULT_ALERT_EMAILS if raw in (None, False) else raw
        return [self._refund_user().email] + [e.strip() for e in extra.split(",")]

    @api.model
    def _email_from(self, company):
        """A sender the Outlook server accepts: its from_filter lists the shop
        domains only, so use the company's own address (a branch falls back
        to its parent)."""
        company = company or self.env.company
        while company and not company.email:
            company = company.parent_id
        return company.email_formatted if company else False

    def _email_staff(self, subject, headline, emails):
        """Email staff (never the customer): one mail.mail, kept after sending,
        and the mail queue run now rather than at its next 12-hourly slot."""
        emails = sorted({e.strip().lower() for e in emails if e and "@" in e})
        if not emails:
            return self.env["mail.mail"]
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        rows = []
        for row in self:
            rows.append(Markup(
                "<tr><td>%s</td><td><a href='%s/odoo/sale.order/%s'>%s</a></td>"
                "<td><a href='%s/odoo/account.move/%s'>%s</a></td><td>%s</td><td>%s</td></tr>") % (
                row.sale_order_id.partner_id.display_name, base, row.sale_order_id.id,
                row.sale_order_id.name, base, row.credit_note_id.id, row.credit_note_id.name,
                row._fmt(row.amount), row._task_text()))
        body = Markup("<p><b>%s</b></p><table border='1' cellpadding='4' style='border-collapse:collapse'>"
                      "<tr><th>Customer</th><th>Order</th><th>Credit note</th><th>Amount</th>"
                      "<th>What to do</th></tr>%s</table>") % (headline, Markup("").join(rows))
        mail = self.env["mail.mail"].sudo().create({
            "subject": subject,
            "body_html": body,
            "email_from": self._email_from(self[:1].company_id),
            "email_to": ",".join(emails),
            "auto_delete": False,
        })
        self.env.ref("mail.ir_cron_mail_scheduler_action").sudo()._trigger()
        return mail

    def _close_task(self, feedback):
        activity = self.activity_id.sudo()
        if activity.exists():
            activity.action_feedback(feedback=feedback)

    def _fmt(self, amount):
        return format_amount(self.env, amount, self.currency_id or self.env.company.currency_id)

    # --------------------------------------------------------------- provider
    def _provider_refunds(self):
        """[{"id", "amount" (dollars, positive), "date" (date)}] for every
        COMPLETED refund the provider holds against this payment."""
        self.ensure_one()
        provider = self.transaction_id.sudo().provider_id
        if not provider:
            raise ProviderReadError(_("the payment's provider is gone"))
        if self.provider_code == "stripe":
            return self._stripe_refunds(provider)
        return self._paypal_refunds(provider)

    def _http(self, method, url, **kw):
        try:
            resp = requests.request(method, url, timeout=TIMEOUT, **kw)
        except requests.RequestException as exc:
            raise ProviderReadError(str(exc)) from exc
        if resp.status_code >= 400:
            raise ProviderReadError("HTTP %s %s" % (resp.status_code, resp.text[:200]))
        return resp.json()

    def _stripe_refunds(self, provider):
        if not getattr(provider, "stripe_secret_key", False):
            raise ProviderReadError(_("no Stripe key on %s", provider.name))
        ref = self.provider_reference
        param = "charge" if ref.startswith("ch_") else "payment_intent"
        data = self._http("GET", "https://api.stripe.com/v1/refunds",
                          params={param: ref, "limit": 100},
                          headers={"Authorization": "Bearer %s" % provider.stripe_secret_key})
        return [{"id": r["id"], "amount": r["amount"] / 100.0,
                 "date": _utc(r["created"]).date()}
                for r in data.get("data", []) if r.get("status") == "succeeded"]

    def _paypal_refunds(self, provider):
        if not (getattr(provider, "paypal_client_id", False) and getattr(provider, "paypal_client_secret", False)):
            raise ProviderReadError(_("no PayPal API credentials on %s", provider.name))
        base = "https://api-m.sandbox.paypal.com" if provider.state == "test" \
            else "https://api-m.paypal.com"
        token = self._http("POST", base + "/v1/oauth2/token", data={"grant_type": "client_credentials"},
                           auth=(provider.paypal_client_id, provider.paypal_client_secret))
        headers = {"Authorization": "Bearer %s" % token["access_token"]}
        capture = self._http("GET", base + "/v2/payments/captures/%s" % self.provider_reference,
                             headers=headers)
        up = [l["href"] for l in capture.get("links", []) if l.get("rel") == "up"]
        if not up:
            # No order link: the capture status alone still says "refunded".
            if capture.get("status") == "REFUNDED":
                amount = float(capture["amount"]["value"])
                return [{"id": "capture:%s" % self.provider_reference, "amount": amount,
                         "date": fields.Date.context_today(self)}]
            return []
        path = requests.utils.urlparse(up[0]).path
        order = self._http("GET", base + path, headers=headers)
        out = []
        for unit in order.get("purchase_units", []):
            for r in unit.get("payments", {}).get("refunds", []):
                if r.get("status") == "COMPLETED":
                    out.append({"id": r["id"], "amount": float(r["amount"]["value"]),
                                "date": fields.Date.from_string((r.get("create_time") or "")[:10])
                                or fields.Date.context_today(self)})
        return out


def _utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
