# -*- coding: utf-8 -*-
"""Raise the Edbert purchase order for a confirmed ecom sale.

Ecom holds no stock; Edbert owns it. This is the ecom-side counterpart of what
`reza_intercompany_warehouse` does for Liaise and Global inside the wholesale
database -- except Edbert is in a DIFFERENT database, so the hand-off runs
through `d3_external_api`, which pushes a confirmed purchase order across as a
sale order.

    ecom sale confirms      -> marked `pending`, nothing remote happens
    cron picks it up        -> purchase order on Edbert, committed, then confirmed
    d3_external_api         -> counterpart sale order in wholesale
    same physical shed      -> the wholesale transfer validates itself, but ONLY
                               when its picking reads `assigned` (see below)
    ecom picks and packs    -> out to the customer

WHY A CRON AND NOT THE CONFIRM ITSELF
Confirming the purchase order hands control to `d3_external_api`, which makes
roughly `2 + 2 x lines` synchronous round trips to another production database,
on a `ServerProxy` that carries NO timeout of its own
(`d3_external_api/wizard/external_api.py:36-38`). Doing that inside the checkout
request would hold an HTTP worker open for as long as wholesale takes to answer.

WHAT THE COMMIT BEFORE THE CONFIRM DOES AND DOES NOT BUY
`button_confirm()` creates and confirms a sale order in the WHOLESALE database.
That is committed on the far side and cannot be undone from here. The local
purchase order is therefore committed FIRST, so a failure in the push leaves the
local order behind, carrying `origin`, for the next pass to find.

It does NOT protect the link to the remote order. `d3_external_api` writes
`purchase.external_api_sale` as a plain local write with no commit behind it
(`models/purchase_order.py:56`), and keeps working afterwards -- line creates, a
remote confirm, a picking read, two `button_validate` calls. A failure in any of
those rolls the stamp away while the wholesale sale order survives, confirmed.
Note the local purchase order reverts to `draft` too, because
`super().button_confirm()` is rolled back with it, so it looks exactly like an
order that was never pushed.

That is why `_reza_resume()` ASKS WHOLESALE before re-confirming a draft order,
matching on `client_order_ref`, which is what `d3_external_api` writes there
(`models/purchase_order.py:50`). Without that check the retry would create a
second wholesale sale order -- the CON/2026/00001 orphan shape, moved rather
than removed.

THE AUTO-VALIDATE IS CONDITIONAL
`d3_external_api` validates the wholesale picking only when it reads `assigned`,
and then validates the local receipt only when the remote call returns exactly
True (`models/purchase_order.py:80-89`). If wholesale cannot reserve, nothing
validates and nothing reports it. On Odoo 17+ `button_validate` can also return
a wizard action instead of validating, which is a silent no-op. Vendor code; the
module's answer is to make its own recovery safe rather than to patch it.

PRICE
`price_unit` is what EDBERT CHARGES THE BRAND, read live from wholesale when the
purchase order is raised: the price on the pricelist of the brand's customer
record in wholesale ("Ecom superstore", which follows BrightEyes - Corporate),
and that pricelist must be the one in the system parameter
`reza_ecom_intercompany_po.edbert_pricelist_id`. Until 2026-10-01 it was
Edbert's `standard_price`. ecom's own `standard_price` is a different figure --
measured 2026-09-02, product 2023 reads 7.61 on ecom against Edbert's 3.3610.

`discount` is passed explicitly as 0.0, and it is load-bearing. `price_unit`,
`name`, `date_planned` and `discount` are ONE stored compute group on
`purchase.order.line`. Supply three and Odoo schedules the compute for the
fourth; it then runs on the real record and assigns all four, replacing the
Edbert price. Supplying all four means the compute is never scheduled. This
matters beyond the first order, because `button_confirm` calls
`_add_supplier_to_product()`, which CREATES a `product.supplierinfo` for Edbert
at whatever price this order used -- so without the guard the second order for a
product is priced from that frozen record. Same stale-price fault as PO01063.

WHERE THE GOODS LAND
The purchase order is created on the company that carries the API credentials,
because `d3_external_api` reads them from `purchase.company_id` and does NOT
walk `parent_id` (`models/purchase_order.py:39-41`). Its receipt therefore lands
in that company's warehouse.

ecom's brands are BRANCHES of ECOM SUPERSTORE PTY LTD and each has its OWN
warehouse -- measured 2026-09-02, deliveries pick from `MJ/Stock` and
`WYN/Stock`, while the root's `EA/Stock` holds nothing. So raising a brand's
order on the root would receive the goods into a shed nothing sells from, and
the customer delivery could never reserve them.

Measured on ecom 2026-09-02 AFTER the rollout: companies 1, 4 and 5 all carry
credentials, and those three are the only ones holding confirmed orders (4, 240
and 313). So no order sits `pending` on a credential gap today.

`_reza_api_company()` therefore returns the order's OWN company or nothing, and
an order whose company carries no credentials is left `pending` with a note
saying so, while the cron drops it from the batch. It is deliberately not a
warning: a log line on an Odoo.sh build reaches a file nobody reads, while a
note on the order is visible on screen. It is deliberately not `failed` either
-- measured on ecom 2026-09-02 only the ROOT company carries credentials, so
marking every brand order failed would burn its five attempts in fifty minutes
and abandon it before anybody copied the settings across. Left pending it
genuinely heals the moment they arrive, with no re-run and no script.

THE TIMEOUT COVERS THIS MODULE'S OWN CALLS ONLY
`RPC_TIMEOUT` is applied to the two reads made here. The vendor push inside
`button_confirm` builds its own `ServerProxy` with no timeout, so the cron can
still stall for an unbounded time on one order. Moving the work off the request
stops that reaching a customer; it does not remove it.
"""
import logging
from collections import defaultdict
import ssl
import xmlrpc.client

import psycopg2

from odoo import _, fields, models
from odoo.exceptions import AccessError
from odoo.osv import expression

_logger = logging.getLogger(__name__)

RPC_TIMEOUT = 60
# Edbert is company 1 in the wholesale database, and `standard_price` there is
# company-dependent -- an unpinned read returns whichever company the remote
# session happens to carry.
WHOLESALE_EDBERT_COMPANY = 1
PRICELIST_PARAM = "reza_ecom_intercompany_po.edbert_pricelist_id"
# How many times the cron re-tries an order that failed before leaving it alone.
MAX_ATTEMPTS = 5


class _TimeoutTransport(xmlrpc.client.SafeTransport):
    """xmlrpc.client offers no timeout; a hung read would stall the cron."""

    def __init__(self, timeout, context=None):
        super().__init__(context=context)
        self._timeout = timeout

    def make_connection(self, host):
        import http.client

        if self._connection and host == self._connection[0]:
            return self._connection[1]
        chost, self._extra_headers, x509 = self.get_host_info(host)
        self._connection = host, http.client.HTTPSConnection(
            chost, None, timeout=self._timeout, context=self.context, **(x509 or {})
        )
        return self._connection[1]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    reza_edbert_purchase_id = fields.Many2one(
        "purchase.order", string="Edbert Purchase", copy=False, readonly=True, index=True,
        help="The intercompany purchase order raised on Edbert for this sale.",
    )
    reza_edbert_status = fields.Selection(
        [
            ("pending", "Waiting to be raised"),
            ("raised", "Raised"),
            ("partial", "Raised, some lines skipped"),
            ("not_needed", "Not needed"),
            ("failed", "Failed"),
        ],
        string="Edbert Status", copy=False, readonly=True, index=True,
    )
    reza_edbert_note = fields.Char(
        string="Edbert Note", copy=False, readonly=True,
        help="Why it was not raised, or which lines were skipped.",
    )
    reza_edbert_transfer_done = fields.Boolean(
        string="Edbert Transfer Complete", copy=False, readonly=True,
        default=False, index=True,
        help="Whether Edbert's delivery and this company's receipt were both "
        "closed. The purchase order can be raised while the transfer is not, "
        "so this is a separate question from the status beside it -- and "
        "without it a transfer that failed would keep its note and never be "
        "tried again.",
    )
    reza_edbert_invoiced = fields.Boolean(
        string="Edbert Invoiced", copy=False, readonly=True, default=False, index=True,
        help="Whether Edbert's customer invoice and this company's vendor bill "
        "were both raised and posted. Separate from the transfer: the goods can "
        "have moved while the money has not been recorded.",
    )
    reza_edbert_attempts = fields.Integer(
        string="Edbert Attempts", copy=False, readonly=True, default=0,
        help="Failed passes so far. The cron stops re-trying at %d." % MAX_ATTEMPTS,
    )

    # ------------------------------------------------------------------ hooks
    def action_confirm(self):
        """Mark it and get out of the way. No remote call happens here."""
        res = super().action_confirm()
        try:
            todo = self.filtered(
                lambda o: not o.reza_edbert_purchase_id and not o.reza_edbert_status
            )
            if todo:
                todo.sudo().write({"reza_edbert_status": "pending"})
        except psycopg2.Error:
            # A database error leaves the cursor aborted, so swallowing it would
            # make the rest of this request fail with "current transaction is
            # aborted" and hide the real cause. Let it out.
            raise
        except Exception:  # noqa: BLE001
            _logger.exception(
                "reza_ecom_intercompany_po: could not mark %s pending", self.ids
            )
        return res

    # ---------------------------------------------------------- public action
    def action_reza_raise_edbert_purchase(self):
        """Button target. MUST be public: Odoo refuses a private method over
        `/web/dataset/call_button` (`check_method_name`, regex `^(_.*|init)$`),
        and view validation only tests that the attribute exists -- so a private
        name installs cleanly and then raises AccessError on every click.

        `groups=` on the view button hides it; it does NOT stop an RPC caller,
        and everything past this point runs under sudo() with the wholesale
        credentials. So the group is re-tested here, server side."""
        if not self.env.user.has_group("purchase.group_purchase_user"):
            raise AccessError(
                _("Only Purchase users can raise the Edbert purchase order."))
        for order in self:
            order._reza_raise_edbert_purchase()
        return True

    # ------------------------------------------------------------------- cron
    def _reza_cron_raise_edbert_purchases(self, limit=50):
        """Raise the Edbert purchase order for orders waiting on it.

        One order per transaction, committed before the next. A failure marks
        that order and moves on -- it never stops the queue. `failed` orders are
        retried up to MAX_ATTEMPTS so one network blip cannot strand a customer,
        and the cap is what stops a permanently broken order filling `limit` and
        starving the ones behind it.
        """
        # The credential test is a DOMAIN leaf, not a filter afterwards. A
        # blocked order never changes status, so it is selected on every pass
        # for ever -- and with `order="id asc"` the blocked ones are the oldest,
        # so filtering after `limit` lets 50 of them fill the batch and the
        # queue does no work at all. Measured on ecom 2026-09-02: only the ROOT
        # company carries credentials, while Mangrove Jacks has 313 confirmed
        # orders and WhatYouNeed 240, so that backlog exists from day one.
        ok = self.env["res.company"].sudo().search(
            [("external_api_url", "!=", False), ("external_api_db", "!=", False)])

        # Raised AFTER dispatch, not on confirmation. Ecom and Edbert share one
        # physical shed, so the goods leave when ecom ships them and the
        # paperwork follows. Raising on confirmation instead creates Edbert
        # orders for goods that may never go, and for quantities that may not
        # match what did.
        #
        # `full` is the only delivered state this waits for. Measured on ecom
        # 2026-09-07 across every confirmed order on the three bridge
        # companies: 559 full, 0 partial, 0 started. A part-shipped order is
        # not a real shape here, so it is deliberately left for a person rather
        # than given machinery nothing exercises.
        base = [
            ("state", "in", ("sale", "done")),
            ("company_id", "in", ok.ids),
            ("delivery_status", "=", "full"),
        ]
        waiting = [("reza_edbert_status", "=", "pending")]
        retry = [
            ("reza_edbert_status", "=", "failed"),
            ("reza_edbert_attempts", "<", MAX_ATTEMPTS),
        ]
        # A purchase order can be raised while its transfer is still open --
        # `_reza_settle_pickings` never raises, so a failure leaves the order
        # marked `raised` with only a note. Without this branch nothing ever
        # goes back to it and both warehouses keep a picking open for good.
        unsettled = [
            ("reza_edbert_status", "in", ("raised", "partial")),
            ("reza_edbert_attempts", "<", MAX_ATTEMPTS),
            "|",
            ("reza_edbert_transfer_done", "=", False),
            # The goods can have moved while the money has not been recorded,
            # so an order whose transfer closed still needs revisiting until
            # both documents exist.
            ("reza_edbert_invoiced", "=", False),
        ]
        # Built with AND/OR rather than written in prefix form: a mis-nested
        # domain here does not fail, it silently selects the wrong orders.
        orders = self.search(
            expression.AND([base, expression.OR([waiting, retry, unsettled])]),
            order="id asc", limit=limit,
        )
        # Kept as a safety net so the domain leaf above and _reza_api_company
        # cannot drift apart silently.
        blocked = orders.filtered(lambda o: not o._reza_api_company())
        if blocked:
            _logger.warning(
                "reza_ecom_intercompany_po: %d order(s) skipped -- no wholesale API "
                "settings on their company: %s",
                len(blocked), ", ".join(sorted(set(blocked.mapped("company_id.name")))))
            orders -= blocked
        _logger.info("reza_ecom_intercompany_po: %d order(s) to process", len(orders))
        for order in orders:
            try:
                order._reza_raise_edbert_purchase()
                order.env.cr.commit()
            except Exception as exc:  # noqa: BLE001
                order.env.cr.rollback()
                _logger.exception("reza_ecom_intercompany_po: %s failed", order.name)
                try:
                    order._reza_mark("failed", str(exc)[:250], bump=True)
                    order.env.cr.commit()
                except Exception:  # noqa: BLE001
                    order.env.cr.rollback()
                    _logger.exception(
                        "reza_ecom_intercompany_po: could not even mark %s failed",
                        order.name,
                    )
        return True

    def _reza_mark(self, status, note=False, purchase=False, bump=False):
        self.ensure_one()
        vals = {"reza_edbert_status": status, "reza_edbert_note": note or False}
        if purchase:
            vals["reza_edbert_purchase_id"] = purchase.id
        if bump:
            vals["reza_edbert_attempts"] = self.reza_edbert_attempts + 1
        self.sudo().write(vals)

    # ------------------------------------------------------------ the company
    def _reza_api_company(self):
        """The company whose credentials and warehouse this order must use.

        The order's OWN company or nothing. Falling back up `parent_id` would
        raise the order on an ancestor, and `d3_external_api` receives into the
        company the purchase order belongs to -- so the goods would arrive in
        the root's warehouse while the customer delivery picks from the brand's.
        Refusing leaves the order `pending` with a note; the cron excludes it
        from its batch entirely, so it neither ages nor fills a slot, and it is
        picked up on the first pass after the settings land.
        """
        self.ensure_one()
        company = self.company_id.sudo()
        if company.external_api_url and company.external_api_db:
            return company
        return self.env["res.company"].browse()

    # ------------------------------------------------------------- the worker
    def _reza_raise_edbert_purchase(self):
        self.ensure_one()
        api = self._reza_api_company()
        if not api:
            # Left `pending`, deliberately, and NOT bumped. This is a
            # configuration gap, not a failure of this order: measured on ecom
            # 2026-09-02 only the root company carries credentials, so with the
            # cron on every brand order would burn its five attempts in fifty
            # minutes and be abandoned before anybody copied the settings
            # across. `pending` costs nothing, stays visible through the note,
            # and genuinely heals the moment the credentials arrive. The cron
            # skips these orders outright so they cannot fill the batch.
            self._reza_mark(
                "pending",
                _("%s carries no wholesale API settings. Raising this order on a parent "
                  "company would receive the goods into that company's warehouse, not "
                  "the one this order sells from.") % self.company_id.display_name)
            return False

        # An order already linked to a purchase order. Never raise a second one,
        # but do finish an unfinished one -- before the fix that added this, a
        # draft link made the order match the cron domain for ever while the
        # worker returned False, and enough of them filled `limit` and starved
        # the queue behind them.
        linked = self.reza_edbert_purchase_id.sudo().exists()
        if linked:
            return self._reza_resume(linked, api)

        if not api.external_api or not api.external_api_purchase:
            self._reza_mark("not_needed", _("Purchase sync is off on %s.") % api.name)
            return False
        vendor = api.external_api_partner_id
        if not vendor:
            self._reza_mark("failed", _("The Edbert vendor is not set on %s.") % api.name,
                            bump=True)
            return False
        # This is the field that becomes the CUSTOMER on the wholesale sale
        # order (`d3_external_api/models/purchase_order.py:48`). It is an
        # Integer holding a remote id, so nothing local validates it; an empty
        # or stale value fails inside button_confirm, after the local purchase
        # order already exists.
        if not api.external_api_purchase_partner:
            self._reza_mark("failed", _("The wholesale customer id is not set on %s.")
                            % api.name, bump=True)
            return False

        Purchase = self.env["purchase.order"].sudo()
        existing = Purchase.search(
            [("origin", "=", self.name), ("partner_id", "=", vendor.id),
             ("company_id", "=", api.id), ("state", "!=", "cancel")], limit=1)
        if existing:
            # Created by an earlier pass whose commit did not land. Adopt it.
            return self._reza_resume(existing, api)

        lines, skipped = self._reza_lines()
        if not lines:
            if skipped:
                # Buyable lines exist and none is mapped. That is a data gap,
                # not a decision -- post-catalogue-rebuild products carry
                # `external_api_id = 0` -- so it stays visible and is retried.
                self._reza_mark("failed", "; ".join(skipped[:4]), bump=True)
            else:
                # Nothing physical on the order at all: services, or a combo
                # whose components are their own lines. Edbert supplies
                # nothing and nothing is wrong. Marking this `failed` would put
                # a red banner on a correct order and retry it five times.
                self._reza_mark(
                    "not_needed", _("Nothing on this order is supplied by Edbert."))
            return False

        prices = self._reza_edbert_prices(api, lines)
        tax = self._reza_purchase_tax(api)
        if not tax:
            # Deliberately NOT added to `skipped`. That list means "these lines
            # were left off the order", and it drives the `partial` status; a
            # tax question is not a missing line and must not be reported as
            # one. It is logged here and noted on the order after the mark.
            _logger.warning(
                "reza_ecom_intercompany_po: %s -- no single tax-exclusive purchase "
                "tax on %s, so the bill may not agree with Edbert's invoice",
                self.name, api.display_name)

        vals_lines, wanted = [], {}
        for l in lines:
            price = prices.get(l["wholesale_id"])
            if price is None:
                skipped.append(_("%s: not found in wholesale") % l["product"].display_name)
                continue
            if price == "archived":
                # An archived wholesale product cannot be sold there, so the
                # remote sale line would be unusable. Skip it here where it is
                # visible rather than failing inside the push.
                skipped.append(_("%s: archived in wholesale") % l["product"].display_name)
                continue
            if not price:
                # A zero price books a permanent zero-value receipt. Refuse it.
                skipped.append(_("%s: Edbert price is zero") % l["product"].display_name)
                continue
            wanted[l["product"].id] = price
            vals_lines.append((0, 0, {
                "product_id": l["product"].id,
                "name": l["product"].display_name,
                "product_qty": l["qty"],
                # Odoo 18 calls this `product_uom`; `product_uom_id` is 19.
                # Use the SALE line's unit, because `qty` is expressed in it.
                "product_uom": l["uom"].id,
                "price_unit": price,
                "date_planned": fields.Datetime.now(),
                "discount": 0.0,               # completes the compute group
                # Passed explicitly for the same reason as the price: left to
                # the compute it resolves to the ROOT company's tax, which
                # reads the price as GST-inclusive while Edbert reads it as
                # GST-exclusive.
                **({"taxes_id": [(6, 0, tax.ids)]} if tax else {}),
            }))
        if not vals_lines:
            self._reza_mark("failed", _("Every line was skipped: %s") % "; ".join(skipped[:4]),
                            bump=True)
            return False

        purchase = Purchase.with_company(api).create({
            "partner_id": vendor.id,
            "company_id": api.id,
            "origin": self.name,
            "external_api": True,              # what d3_external_api filters on
            "order_line": vals_lines,
        })

        # Prove the Edbert price survived the create, matched on PRODUCT rather
        # than on position -- line order is not guaranteed.
        wrong = [
            "%s: %.4f not %.4f" % (pl.product_id.display_name, pl.price_unit,
                                   wanted[pl.product_id.id])
            for pl in purchase.order_line
            if pl.product_id.id in wanted
            and abs(pl.price_unit - wanted[pl.product_id.id]) > 0.0001
        ]
        if wrong:
            raise ValueError(_("The Edbert price was overwritten on create: %s")
                             % "; ".join(wrong[:3]))

        # Same check for the tax. `taxes_id` is a stored compute like the
        # price, so a change in how Odoo schedules it would silently put the
        # root's tax-inclusive GST back and reintroduce the 1/11 gap.
        if tax:
            mistaxed = [
                pl.product_id.display_name for pl in purchase.order_line
                if pl.taxes_id != tax
            ]
            if mistaxed:
                raise ValueError(
                    _("The purchase tax was overwritten on create for: %s")
                    % ", ".join(mistaxed[:3]))

        # Record the link and COMMIT before anything remote happens, so a
        # failure in the push cannot leave an unrecorded wholesale order.
        status = "partial" if skipped else "raised"
        self._reza_mark(status, ("; ".join(skipped[:4]) or False), purchase)
        if not tax:
            self._reza_note(
                _("No tax-exclusive purchase tax on %s, so this bill may not "
                  "agree with Edbert's invoice.") % api.display_name)
        self.env.cr.commit()

        confirmed = self._reza_confirm(purchase)
        if confirmed:
            self._reza_settle_and_record(purchase)
        return confirmed

    # ---------------------------------------------------------- the recovery
    def _reza_resume(self, purchase, api):
        """Finish a purchase order this sale is already linked to.

        Never creates. Only `purchase` and `done` count as finished. A cancelled
        one is reported, because it needs a person. Anything still open is the
        interesting case: it may ALREADY have a confirmed counterpart in
        wholesale that was rolled away locally, so wholesale is asked before it
        is re-confirmed.
        """
        self.ensure_one()
        if purchase.state == "cancel":
            self._reza_mark(
                "failed",
                _("Purchase order %s was cancelled. Raise a new one by hand.")
                % purchase.name, bump=True)
            return False

        if purchase.state in ("purchase", "done"):
            if not purchase.external_api_sale:
                # Confirmed here and never pushed. `d3_external_api` stamps
                # external_api_sale immediately after it creates the remote
                # order, and a failure after that rolls the local state back to
                # draft as well -- so a CONFIRMED order carrying no stamp can
                # only mean the push never ran (the flag was off at the time).
                # Confirming again would not re-run it: core's button_confirm
                # skips a confirmed order. It needs a person.
                self._reza_mark(
                    "failed",
                    _("Purchase order %s is confirmed but was never sent to wholesale. "
                      "Check its No Sync flag, then raise the wholesale order by hand.")
                    % purchase.name, bump=True)
                return False
            self._reza_mark_done(purchase)
            # The order was already linked and confirmed, so the only thing
            # that can still be outstanding is the transfer. Without this a
            # settle that failed once is never attempted again.
            self._reza_settle_and_record(purchase)
            return purchase

        if purchase.state not in ("draft", "sent"):
            # `to approve`. Core's button_confirm acts on draft and sent only,
            # so calling it would change nothing and cost a remote round trip.
            self._reza_mark(
                "failed",
                _("Purchase order %s is waiting for approval, so it cannot be sent to "
                  "wholesale yet.") % purchase.name, bump=True)
            return False

        # draft or sent -- unfinished, and possibly already half-pushed.
        if not purchase.external_api_sale:
            remote = self._reza_find_remote_sale(api, purchase.name)
            if remote:
                # The vendor creates the remote order EMPTY, stamps it locally,
                # then creates the remote lines ONE call at a time
                # (`d3_external_api/models/purchase_order.py:53-60`). Each of
                # those lands on the far side while the local transaction can
                # still roll back, so a partial line set is a WIDER window than
                # an empty one. Adopting either would under-supply the customer
                # silently, so both are refused. `!=` not `<`: extra lines need
                # a person just as much as missing ones do.
                expected = len(purchase.order_line.filtered(
                    lambda l: l.product_id.external_api_id))
                if remote["line_count"] != expected:
                    self._reza_mark(
                        "failed",
                        _("Wholesale order %s already exists for %s with %s line(s), "
                          "not the %s expected. Fix it in wholesale, then clear this "
                          "link.") % (remote["name"], purchase.name,
                                      remote["line_count"], expected),
                        bump=True)
                    return False
                # Re-stamp the link the rollback lost, and commit it before the
                # confirm so it cannot be lost a second time.
                purchase.sudo().external_api_sale = remote["id"]
                self.env.cr.commit()
                _logger.info(
                    "reza_ecom_intercompany_po: re-linked %s to wholesale order %s",
                    purchase.name, remote["name"])
        confirmed = self._reza_confirm(purchase)
        if confirmed:
            # The create path marks BEFORE it confirms, so it needs no mark
            # here. The resume path does: without this an order recovered from
            # `failed` keeps that status and its stale note, and goes on showing
            # "The Edbert purchase order was not raised" over a purchase order
            # that is confirmed and pushed. Mark first, then settle, so a note
            # the settle leaves is not overwritten by the mark.
            self._reza_mark_done(purchase)
            self._reza_settle_and_record(purchase)
        return confirmed

    def _reza_mark_done(self, purchase):
        """Record a purchase order that really did reach wholesale.

        The partial state is RECOMPUTED from the records, never read off the
        current status. Any failure between the create-path mark and a later
        successful resume overwrites both the status and the note -- the cron
        handler does it, and so does `_reza_confirm` -- so deriving `partial`
        from `reza_edbert_status` silently loses the skipped-line list and
        records a clean success over an order Edbert is only part-supplying.
        That is the exact fault this module exists to prevent, arriving through
        the fix for it.

        Comparing the purchase order's products against the sale's buyable
        lines cannot be lost that way, and it catches every reason a line was
        left off -- unmapped, archived in wholesale, or zero price.
        """
        self.ensure_one()
        wanted, skipped = self._reza_lines()
        bought = set(purchase.order_line.mapped("product_id").ids)
        notes = list(skipped) + [
            _("%s: not bought from Edbert") % l["product"].display_name
            for l in wanted if l["product"].id not in bought
        ]
        if notes:
            self._reza_mark("partial", "; ".join(notes[:4]), purchase)
        else:
            self._reza_mark("raised", False, purchase)

    def _reza_invoice(self, purchase):
        """Raise and post BOTH documents, once the goods have actually moved.

        Edbert invoices the ecom brand company; that company records the
        matching vendor bill, carrying Edbert's invoice number as its
        reference. That number is the only thing tying the two together across
        two databases.

        `d3_external_api` already asks wholesale to raise its invoice, from its
        own override of `action_create_invoice` -- so that call is reused rather
        than duplicated. What it does not do is post either document, check that
        they agree, or say anything when its remote call fails (it ends in a
        bare `except: return False`). This adds all three.

        NOTHING IS POSTED UNTIL THE TWO AGREE. Until 2026-09-07 the two sides
        read the same `price_unit` with different tax treatments and were out by
        1/11 on every line; posting into that would have put the error in both
        ledgers automatically. Both documents are left in draft instead, and the
        difference is named on the order.

        Like the transfer, it NEVER raises. The goods have gone and the purchase
        order is committed; a money document that could not be raised is a thing
        to report and retry, not a reason to fail the order.
        """
        self.ensure_one()
        if self.reza_edbert_invoiced:
            return True
        if not purchase.external_api_sale:
            return False
        try:
            proxy, db, uid, pwd = self._reza_wholesale_proxy(self._reza_api_company())
            remote_id = purchase.external_api_sale
            ctx = {"skip_reza_fuel_surcharge_sync": True, "skip_tax_update": True}

            # 1. The vendor bill here. Its creation is also what asks wholesale
            #    to raise its own invoice.
            bill = purchase.invoice_ids.filtered(lambda m: m.state != "cancel")
            if not bill:
                # Core RAISES here rather than returning quietly when nothing is
                # invoiceable (purchase/models/purchase_order.py:694). Caught by
                # the blanket handler below, that turns an ordinary "the goods
                # are not recorded as received yet" into a reported failure, so
                # it is tested for first.
                if purchase.invoice_status != "to invoice":
                    self._reza_note(
                        _("%(po)s is %(status)s, so there is nothing to bill yet.")
                        % {"po": purchase.name, "status": purchase.invoice_status})
                    return False
                purchase.sudo().action_create_invoice()
                purchase.invalidate_recordset(["invoice_ids"])
                bill = purchase.invoice_ids.filtered(lambda m: m.state != "cancel")
            if not bill:
                self._reza_note(_("No vendor bill could be created for %s.") % purchase.name)
                return False
            bill = bill[0]

            # 2. Wholesale's invoice. The vendor module swallows its own
            #    failures, so if it produced nothing, ask for it here.
            remote = proxy.execute_kw(db, uid, pwd, "sale.order", "read", [[remote_id]],
                                      {"fields": ["name", "invoice_ids", "invoice_status"]})[0]
            if not remote["invoice_ids"]:
                wiz = proxy.execute_kw(
                    db, uid, pwd, "sale.advance.payment.inv", "create",
                    [{"advance_payment_method": "delivered"}],
                    {"context": dict(ctx, active_model="sale.order",
                                     active_ids=[remote_id], active_id=remote_id)})
                proxy.execute_kw(db, uid, pwd, "sale.advance.payment.inv",
                                 "create_invoices", [[wiz]], {"context": ctx})
                remote = proxy.execute_kw(db, uid, pwd, "sale.order", "read", [[remote_id]],
                                          {"fields": ["name", "invoice_ids"]})[0]
            if not remote["invoice_ids"]:
                self._reza_note(_("Wholesale %s produced no invoice.") % remote["name"])
                return False

            inv = proxy.execute_kw(db, uid, pwd, "account.move", "read",
                                   [remote["invoice_ids"][:1]],
                                   {"fields": ["name", "state", "amount_untaxed",
                                               "amount_total"]})[0]

            # 3. Agreement, BEFORE either document is posted.
            gap = abs(bill.amount_untaxed - inv["amount_untaxed"])
            if gap > 0.01:
                self._reza_note(
                    _("Edbert invoice %(n)s is %(theirs).2f ex GST but this bill is "
                      "%(ours).2f. Neither was posted.")
                    % {"n": inv["name"], "theirs": inv["amount_untaxed"],
                       "ours": bill.amount_untaxed})
                _logger.warning(
                    "reza_ecom_intercompany_po: %s -- invoice %s %.2f vs bill %.2f",
                    self.name, inv["name"], inv["amount_untaxed"], bill.amount_untaxed)
                return False

            # 4. They agree. Post both.
            if inv["state"] == "draft":
                proxy.execute_kw(db, uid, pwd, "account.move", "action_post",
                                 [[inv["id"]]], {"context": ctx})
                inv = proxy.execute_kw(db, uid, pwd, "account.move", "read", [[inv["id"]]],
                                       {"fields": ["name", "state", "amount_untaxed",
                                                   "amount_total"]})[0]
            if inv["state"] != "posted":
                self._reza_note(_("Edbert invoice %(n)s is %(s)s, so the bill was not "
                                  "posted.") % {"n": inv["name"], "s": inv["state"]})
                return False

            if bill.state == "draft":
                bill.sudo().write({"ref": inv["name"],
                                   "invoice_date": bill.invoice_date or fields.Date.today()})
                bill.sudo().action_post()
            if bill.state != "posted":
                self._reza_note(_("Vendor bill %(b)s for Edbert invoice %(n)s is %(s)s.")
                                % {"b": bill.name, "n": inv["name"], "s": bill.state})
                return False

            _logger.info(
                "reza_ecom_intercompany_po: %s billed %s against Edbert invoice %s (%.2f ex)",
                self.name, bill.name, inv["name"], inv["amount_untaxed"])
            return True
        except Exception:  # noqa: BLE001
            _logger.exception("reza_ecom_intercompany_po: could not invoice %s", self.name)
            self._reza_note(_("The goods moved, but the invoice could not be raised. "
                              "It will be tried again."))
            return False

    def _reza_invoice_and_record(self, purchase):
        self.ensure_one()
        done = bool(self._reza_invoice(purchase))
        if done != self.reza_edbert_invoiced:
            self.sudo().reza_edbert_invoiced = done
        return done

    def _reza_settle_and_record(self, purchase):
        """Settle the transfer and remember whether it closed.

        `_reza_settle_pickings` deliberately never raises -- the purchase order
        is already raised and committed, and a transfer that could not be
        closed must not report the order as failed. The cost of that is that a
        failure leaves nothing to act on but a note. This records the outcome,
        so the cron can come back to it.
        """
        self.ensure_one()
        done = bool(self._reza_settle_pickings(purchase))
        if done != self.reza_edbert_transfer_done:
            self.sudo().reza_edbert_transfer_done = done
        if done:
            # Only after the transfer closes. Invoicing goods that have not
            # moved would bill for something neither warehouse has recorded.
            self._reza_invoice_and_record(purchase)
        return done

    def _reza_settle_pickings(self, purchase):
        """Complete the transfer `d3_external_api` could not.

        WHY IT CANNOT. The connector validates the wholesale picking and then
        does `if res is True:` before validating the ecom receipt
        (`models/purchase_order.py:79-90`). On the Edbert databases
        `reza_auto_post_print_invoice_enabled` is set, so
        `reza_starshipit_consolidation.button_validate` hands back the
        dispatch-confirmation WIZARD instead of validating
        (`stock_picking.py:200`). A dict is not True, so BOTH sides stay open
        and nothing says why. Passing `reza_skip_auto_invoice_prompt=True` is
        what reaches `super()`.

        This is the paperwork leg of a transfer between two warehouses in the
        same physical shed, so it completes without a picker. It NEVER raises:
        the purchase order is already raised and committed, and an order that
        reached wholesale must not be reported as failed because a transfer
        could not be closed. What it cannot do, it says on the order.
        """
        self.ensure_one()
        if not purchase.external_api_sale:
            return False
        try:
            proxy, db, uid, pwd = self._reza_wholesale_proxy(self._reza_api_company())
            ctx = {"skip_reza_fuel_surcharge_sync": True, "skip_tax_update": True,
                   "reza_skip_auto_invoice_prompt": True}
            rows = proxy.execute_kw(db, uid, pwd, "sale.order", "search_read",
                                    [[["id", "=", purchase.external_api_sale]]],
                                    {"fields": ["name", "picking_ids"]})
            if not rows or not rows[0].get("picking_ids"):
                return False
            remote_name = rows[0]["name"]
            pickings = proxy.execute_kw(db, uid, pwd, "stock.picking", "read",
                                        [rows[0]["picking_ids"], ["name", "state"]])
            settled, stuck = [], []
            for p in pickings:
                if p["state"] == "done":
                    settled.append(p["name"])
                    continue
                if p["state"] != "assigned":
                    # Not reserved -- wholesale cannot supply it yet. Expected,
                    # not a fault; the shed will pick it when stock arrives.
                    stuck.append("%s is %s" % (p["name"], p["state"]))
                    continue
                proxy.execute_kw(db, uid, pwd, "stock.picking", "button_validate",
                                 [[p["id"]]], {"context": ctx})
                after = proxy.execute_kw(db, uid, pwd, "stock.picking", "read",
                                         [[p["id"]], ["name", "state"]])[0]
                (settled if after["state"] == "done" else stuck).append(
                    after["name"] if after["state"] == "done"
                    else "%s stayed %s" % (after["name"], after["state"]))
            if stuck:
                _logger.warning(
                    "reza_ecom_intercompany_po: %s -> %s not fully dispatched: %s",
                    self.name, remote_name, "; ".join(stuck))
                self._reza_note(_("Wholesale %s is not fully dispatched: %s")
                                % (remote_name, "; ".join(stuck[:3])))
                return False
            # Wholesale has shipped. Receive it here.
            receipts = purchase.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            for r in receipts:
                r.action_assign()
                for move in r.move_ids:
                    move.quantity = move.product_uom_qty
                    move.picked = True
                r.with_context(skip_backorder=True).button_validate()
            bad = purchase.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            if bad:
                self._reza_note(_("Wholesale shipped %s but the receipt %s is still %s.")
                                % (remote_name, bad[0].name, bad[0].state))
                return False
            _logger.info("reza_ecom_intercompany_po: %s settled %s and received it",
                         self.name, ", ".join(settled))
            return True
        except Exception:  # noqa: BLE001
            _logger.exception(
                "reza_ecom_intercompany_po: could not settle the transfer for %s", self.name)
            self._reza_note(_("The purchase order was raised, but the transfer could not "
                              "be completed automatically. Validate it by hand."))
            return False

    def _reza_note(self, text):
        """Append to the note WITHOUT touching status or attempts."""
        self.ensure_one()
        old = self.reza_edbert_note or ""
        self.sudo().write({"reza_edbert_note": ((old + " | ") if old else "") + text})

    def _reza_confirm(self, purchase):
        """Confirm the purchase order -- this is the leg that reaches wholesale."""
        self.ensure_one()
        purchase.button_confirm()
        if purchase.state not in ("purchase", "done"):
            # `two_step` double validation leaves it at `to approve`. Marking
            # this `raised` would report success, hide the note (the banner
            # renders it on `failed`, `partial`, `not_needed` and `pending`
            # -with-a-note, but never on `raised`) and drop the order out of the
            # cron domain for good. Mark it failed so it stays visible.
            self._reza_mark(
                "failed",
                _("Purchase order %s is %s, not confirmed.") % (purchase.name, purchase.state),
                purchase, bump=True)
            return False
        _logger.info("reza_ecom_intercompany_po: %s -> %s (%s)",
                     self.name, purchase.name, purchase.state)
        return purchase

    def _reza_purchase_tax(self, company):
        """The tax to put on the Edbert bill lines, or an empty recordset.

        It must be a tax THIS company owns. The branch companies here own no
        tax of their own by default and fall back to the root's GST -- and the
        root reads a price as tax-INCLUSIVE while Edbert reads the same number
        as tax-EXCLUSIVE. The identical `price_unit` then means two different
        things, and the bill can never match the invoice.

        Measured on production 2026-09-07 across all nine bridge orders: every
        pair was out by exactly 1/11. For one Tread Thong at 4.18889, Edbert
        invoiced 4.19 ex / 4.61 inc while ecom recorded 3.81 ex / 4.19 inc.

        A tax the company owns is evaluated against that company, which is
        tax-exclusive like Edbert, so both sides read the number the same way.
        Anything other than exactly one candidate is left alone rather than
        guessed at -- the caller records that it fell back.
        """
        taxes = self.env["account.tax"].sudo().search([
            ("company_id", "=", company.id),
            ("type_tax_use", "=", "purchase"),
            ("active", "=", True),
        ])
        exclusive = taxes.filtered(lambda t: not t.price_include)
        return exclusive if len(exclusive) == 1 else self.env["account.tax"]

    def _reza_lines(self):
        """Which sale lines Edbert must supply, and against which product.

        The quantity is what ecom DELIVERED, not what the customer ordered.
        The purchase order is raised after dispatch, so this is the paperwork
        for goods that have already physically left the shared shed, and it
        must match them.

        That also handles a case no separate check would catch: a delivery
        validated with no backorder CANCELS the unpicked moves, and the order
        then reads `delivery_status = full` with a line short. Buying the
        ordered quantity would bill Edbert for goods that never moved; buying
        the delivered quantity is right either way.
        """
        self.ensure_one()
        out, skipped = [], []
        for line in self.order_line:
            if line.display_type or not line.product_id:
                continue
            product = line.product_id
            # Odoo 18 types are consu / service / combo. Only goods are bought;
            # a combo is a wrapper whose components are their own lines.
            if product.type in ("service", "combo"):
                continue
            # Measured on ecom 2026-09-07: every waiting order carried the
            # shipping line at qty_delivered 0, which this drops. Edbert does
            # not supply freight.
            if line.qty_delivered <= 0:
                continue
            if not product.external_api_id:
                skipped.append(_("%s: not mapped to wholesale") % product.display_name)
                continue
            out.append({"product": product,
                        "qty": line.qty_delivered,
                        "uom": line.product_uom,
                        "wholesale_id": product.external_api_id})
        return out, skipped

    # ------------------------------------------------------------ wholesale IO
    def _reza_wholesale_proxy(self, api):
        """(execute_kw proxy, db, uid, password) for the wholesale database."""
        url, db = api.external_api_url, api.external_api_db
        user, pwd = api.external_api_username, api.external_api_password
        if not (url and db and user and pwd):
            raise ValueError(_("The wholesale API credentials are not set on %s.") % api.name)
        if not url.lower().startswith("https://"):
            # _TimeoutTransport extends SafeTransport, so an http:// value
            # would attempt TLS on port 80 and fail with an obscure error.
            raise ValueError(_("The wholesale API address on %s must start with https://.")
                             % api.name)
        ctx = ssl.create_default_context()
        common = xmlrpc.client.ServerProxy(
            "%s/xmlrpc/2/common" % url,
            transport=_TimeoutTransport(RPC_TIMEOUT, context=ctx))
        uid = common.authenticate(db, user, pwd, {})
        if not uid:
            # Do not name the database or the login: this string is shown to
            # any sales user through the banner on the order.
            raise ValueError(_("Could not sign in to the wholesale system."))
        proxy = xmlrpc.client.ServerProxy(
            "%s/xmlrpc/2/object" % url,
            transport=_TimeoutTransport(RPC_TIMEOUT, context=ctx))
        return proxy, db, uid, pwd

    def _reza_find_remote_sale(self, api, purchase_name):
        """The wholesale sale order `d3_external_api` would have created, if any.

        Matched on `client_order_ref`, which is what it writes there
        (`d3_external_api/models/purchase_order.py:50`). Returns the id, name
        and LINE COUNT -- the line count is what separates a complete remote
        order from a half-built one.
        """
        self.ensure_one()
        proxy, db, uid, pwd = self._reza_wholesale_proxy(api)
        rows = proxy.execute_kw(
            db, uid, pwd, "sale.order", "search_read",
            [[["client_order_ref", "=", purchase_name], ["state", "!=", "cancel"]]],
            {"fields": ["name", "state", "order_line"], "limit": 2,
             "context": {"allowed_company_ids": [WHOLESALE_EDBERT_COMPANY]}})
        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError(
                _("More than one wholesale order already quotes %s. Sort it out there "
                  "before this one is re-tried.") % purchase_name)
        r = rows[0]
        return {"id": r["id"], "name": r["name"], "state": r["state"],
                "line_count": len(r.get("order_line") or [])}

    def _reza_expected_pricelist_id(self):
        """The wholesale pricelist the brands must be charged on.

        Read from a system parameter rather than trusted from wholesale: if a
        brand's customer record in Edbert is ever left on Default, wholesale
        would answer with full list price and nothing would look wrong.
        `get_param` returns False for a missing key and `int(False)` is 0, so
        the raw value is tested BEFORE the cast (recorded in CLAUDE.md).
        """
        raw = self.env["ir.config_parameter"].sudo().get_param(PRICELIST_PARAM)
        if raw in (None, False, "") or not str(raw).strip().isdigit() or int(raw) <= 0:
            raise ValueError(_("The Edbert pricelist for intercompany orders is not set "
                               "(system parameter %s).") % PRICELIST_PARAM)
        return int(raw)

    def _reza_edbert_prices(self, api, lines):
        """What Edbert charges this brand per wholesale product, read live.

        Wholesale prices it on the pricelist of the brand's OWN customer record
        there (`external_api_purchase_partner`) through
        `res.partner.reza_external_api_prices` in wholesale's `d3_external_api`.
        It used to be Edbert's cost; Reza's call 2026-10-01 is that the brands
        buy at the Bright Eyes price, through the "Ecom superstore" pricelist.

        Returns {wholesale_id: price}. A missing key means wholesale does not
        have that id; the string "archived" means it has it but cannot sell it.
        `search_read` is used rather than `read` because `read` can raise
        MissingError on a stale id, which would fail the whole order instead of
        skipping one line. Raises when wholesale priced on any pricelist other
        than the configured one.
        """
        self.ensure_one()
        wholesale_ids = sorted({l["wholesale_id"] for l in lines})
        if not wholesale_ids:
            return {}
        expected = self._reza_expected_pricelist_id()
        qty = defaultdict(float)
        for l in lines:
            qty[l["wholesale_id"]] += l["qty"]
        proxy, db, uid, pwd = self._reza_wholesale_proxy(api)
        ctx = {"allowed_company_ids": [WHOLESALE_EDBERT_COMPANY], "active_test": False}
        rows = proxy.execute_kw(
            db, uid, pwd, "product.product", "search_read",
            [[["id", "in", wholesale_ids]]],
            {"fields": ["active", "display_name"], "context": ctx})
        priced = proxy.execute_kw(
            db, uid, pwd, "res.partner", "reza_external_api_prices",
            [[api.external_api_purchase_partner], [[wid, qty[wid]] for wid in wholesale_ids]],
            {"company_id": WHOLESALE_EDBERT_COMPANY, "context": ctx})
        if priced.get("pricelist_id") != expected:
            raise ValueError(_(
                "Edbert priced this order on pricelist \"%s\", not the agreed one (id %s). "
                "Set this brand's customer in Edbert to the right pricelist.")
                % (priced.get("pricelist_name"), expected))
        prices = priced.get("prices") or {}
        out = {}
        for r in rows:
            if not r.get("active"):
                _logger.warning(
                    "reza_ecom_intercompany_po: wholesale product %s (%s) is archived",
                    r["id"], r.get("display_name"))
                out[r["id"]] = "archived"
                continue
            out[r["id"]] = prices.get(str(r["id"])) or 0.0
        return out
