# -*- coding: utf-8 -*-
"""Send an item a customer returned back to Edbert, on paper, in both databases.

Ecom holds no stock of its own: the Edbert bridge buys every item from Edbert
once it ships. So when a customer sends an item back, it must go back to
Edbert too. If it stayed in the ecom warehouse, the next order that shipped it
would buy it from Edbert a second time. Physically nothing moves: both
companies share one shed.

One row per product per exchange. The work is four steps, each recorded on the
row as it completes, so a run that stops half way resumes where it stopped and
never repeats a step:

    1. local_return_id      ecom receipt returned (branch stock -> vendor)
    2. remote_return_name   Edbert delivery returned (customer -> Edbert stock)
    3. vendor_refund_id     vendor credit note here, draft
    4. remote_refund_id     Edbert credit note there, draft
    then: both amounts agree -> post both; otherwise leave both draft and say so.

The ORDER of 1 and 2 copies `purchase_order.py` in reza_ecom_intercompany_po:
ecom first, so a failure in between leaves a unit missing (found at stocktake)
rather than counted twice (never found).

NOTHING IS POSTED UNTIL THE TWO CREDITS AGREE -- the same rule the bridge uses
for the bill and the invoice.

Runs from a cron, one row per transaction, never inside the button's request:
a remote step that succeeds must not be undone on the far side by a local
rollback that it cannot see. The button only queues the row and triggers the
cron.

Remote steps are idempotent by a MARKER ("Exchange <row name>") written onto
the Edbert return picking's `origin` and into the credit note's reversal
reason. Before it creates either, the step searches for the marker and adopts
what it finds -- so a run that crashed after the remote create, before the
local write, does not create a second one.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
# Remote writes reach a database whose sale-order and picking hooks need these
# (see reza_ecom_intercompany_po/models/purchase_order.py).
REMOTE_CTX = {"skip_reza_fuel_surcharge_sync": True, "skip_tax_update": True,
              "reza_skip_auto_invoice_prompt": True, "skip_backorder": True}


class RezaEdbertReturn(models.Model):
    _name = "reza.edbert.return"
    _description = "Exchanged item going back to Edbert"
    _order = "id desc"

    name = fields.Char(required=True, readonly=True, copy=False, default="/")
    sale_order_id = fields.Many2one("sale.order", required=True, readonly=True,
                                    index=True, ondelete="restrict")
    purchase_id = fields.Many2one("purchase.order", string="Edbert Purchase",
                                  required=True, readonly=True, ondelete="restrict")
    company_id = fields.Many2one(related="purchase_id.company_id", store=True)
    product_id = fields.Many2one("product.product", required=True, readonly=True)
    qty = fields.Float("Quantity", required=True, readonly=True,
                       digits="Product Unit of Measure")
    state = fields.Selection([
        ("pending", "Waiting"),
        ("mismatch", "Credits disagree"),
        ("failed", "Failed"),
        ("done", "Done"),
    ], default="pending", required=True, readonly=True, index=True)
    note = fields.Char(readonly=True)
    attempts = fields.Integer(readonly=True, default=0)

    local_return_id = fields.Many2one("stock.picking", string="Ecom Return", readonly=True)
    remote_return_name = fields.Char("Edbert Return", readonly=True)
    vendor_refund_id = fields.Many2one("account.move", string="Vendor Credit", readonly=True)
    remote_refund_id = fields.Integer("Edbert Credit Note Id", readonly=True)
    remote_refund_name = fields.Char("Edbert Credit Note", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                order = self.env["sale.order"].browse(vals["sale_order_id"])
                n = self.search_count([("sale_order_id", "=", order.id)]) + 1
                vals["name"] = "%s-R%d" % (order.name, n)
        return super().create(vals_list)

    def _get_marker(self):
        self.ensure_one()
        return "[Exchange %s]" % self.name

    # ---------------------------------------------------------- public action
    def action_retry(self):
        """Button target, so public. Everything past here runs remote calls
        with the wholesale credentials, so the group is re-tested server side:
        `groups=` on the button only hides it."""
        if not self.env.user.has_group("purchase.group_purchase_user"):
            raise AccessError(_("Only Purchase users can send items back to Edbert."))
        for row in self.filtered(lambda r: r.state != "done"):
            row.sudo().write({"attempts": 0})
            row.sudo()._process()
        return True

    # ------------------------------------------------------------------- cron
    @api.model
    def _cron_process(self, limit=20):
        if not self.env.su and not self.env.user.has_group("purchase.group_purchase_user"):
            raise AccessError(_("Only Purchase users can send items back to Edbert."))
        rows = self.sudo().search([
            ("state", "in", ("pending", "failed")),
            ("attempts", "<", MAX_ATTEMPTS),
        ], order="id asc", limit=limit)
        for row in rows:
            row._process()
            row.env.cr.commit()
        return True

    def _process(self):
        """Run what is left of the four steps. Never raises: a failure is
        recorded on the row and retried."""
        self.ensure_one()
        cr = self.env.cr
        try:
            # Each step in its own savepoint and committed after it, so a
            # failure undoes only the step it happened in, and every remote
            # change that did happen is matched by a local record of it.
            for step in (self._step_local_return, self._step_remote_return,
                         self._step_vendor_refund, self._step_remote_refund,
                         self._step_post):
                with cr.savepoint():
                    step()
                cr.commit()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("reza_exchange_shipped: %s failed", self.name)
            self.invalidate_recordset()
            self.write({"state": "failed", "note": str(exc)[:500],
                        "attempts": self.attempts + 1})
            self.sale_order_id.message_post(body=_(
                "Sending %(qty)s × %(product)s back to Edbert failed (%(row)s): %(err)s",
                qty=self.qty, product=self.product_id.display_name, row=self.name,
                err=str(exc)[:300]))
        return self.state == "done"

    # ------------------------------------------------------------------ steps
    def _step_local_return(self):
        """Return `qty` of the product on the Edbert receipt: the item leaves
        the branch warehouse again, so the warehouse ends where it started."""
        if self.local_return_id:
            return
        prec = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        moves = self.purchase_id.picking_ids.move_ids.filtered(
            lambda m: m.state == "done" and m.product_id == self.product_id
            and m.picking_id.picking_type_id.code == "incoming"
            and not m.origin_returned_move_id)
        if not moves:
            raise UserError(_("%(po)s has no received %(product)s to return.",
                              po=self.purchase_id.name, product=self.product_id.display_name))
        picking = moves.sorted("id", reverse=True)[0].picking_id
        wizard = self.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking",
        ).create({"picking_id": picking.id})
        remaining = self.qty
        for line in wizard.product_return_moves:
            if line.product_id != self.product_id or float_is_zero(remaining, precision_digits=prec):
                line.quantity = 0.0
                continue
            take = min(line.move_quantity, remaining)
            line.quantity = take
            remaining -= take
        if float_compare(remaining, 0.0, precision_digits=prec) > 0:
            raise UserError(_("%(pick)s holds less than %(qty)s of %(product)s to return.",
                              pick=picking.name, qty=self.qty,
                              product=self.product_id.display_name))
        ret = wizard._create_return()
        ret.origin = self._get_marker()
        for move in ret.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        ret.with_context(skip_backorder=True).button_validate()
        if ret.state != "done":
            raise UserError(_("Ecom return %(ret)s came back %(state)s.",
                              ret=ret.name, state=ret.state))
        self.local_return_id = ret

    def _remote(self):
        remote = self.purchase_id._reza_remote()
        if not remote:
            raise UserError(_("%s carries no wholesale API settings.")
                            % self.purchase_id.company_id.display_name)
        return remote

    def _wholesale_id(self):
        wid = self.product_id.external_api_id
        if not wid:
            raise UserError(_("%s is not mapped to wholesale.") % self.product_id.display_name)
        return wid

    def _remote_sale(self, proxy, db, uid, pwd):
        sid = self.purchase_id.external_api_sale
        rows = proxy.execute_kw(db, uid, pwd, "sale.order", "read", [[sid]],
                                {"fields": ["name", "picking_ids", "invoice_ids"]}) if sid else []
        if not rows:
            raise UserError(_("%s has no Edbert sale order.") % self.purchase_id.name)
        return rows[0]

    def _step_remote_return(self):
        """Return `qty` of the product on Edbert's delivery: back into Edbert's
        stock."""
        if self.remote_return_name:
            return
        proxy, db, uid, pwd = self._remote()
        wid = self._wholesale_id()
        existing = proxy.execute_kw(db, uid, pwd, "stock.picking", "search_read",
                                    [[["origin", "=", self._get_marker()],
                                      ["state", "!=", "cancel"]]],
                                    {"fields": ["name", "state"]})
        if existing:
            rid, rname = existing[0]["id"], existing[0]["name"]
        else:
            sale = self._remote_sale(proxy, db, uid, pwd)
            pickings = proxy.execute_kw(
                db, uid, pwd, "stock.picking", "read", [sale["picking_ids"]],
                {"fields": ["name", "state", "picking_type_code", "return_id"]}
            ) if sale["picking_ids"] else []
            outs = [p for p in pickings if p["state"] == "done"
                    and p["picking_type_code"] == "outgoing" and not p.get("return_id")]
            if not outs:
                raise UserError(_("Edbert order %s has no completed delivery.") % sale["name"])
            out = sorted(outs, key=lambda p: p["id"], reverse=True)[0]
            ctx = dict(REMOTE_CTX, active_id=out["id"], active_model="stock.picking")
            wiz = proxy.execute_kw(db, uid, pwd, "stock.return.picking", "create",
                                   [{"picking_id": out["id"]}], {"context": ctx})
            lines = proxy.execute_kw(db, uid, pwd, "stock.return.picking.line", "search_read",
                                     [[["wizard_id", "=", wiz]]],
                                     {"fields": ["product_id", "move_quantity"]})
            remaining = self.qty
            for line in lines:
                pid = line["product_id"][0] if line["product_id"] else False
                take = min(line["move_quantity"], remaining) if pid == wid else 0.0
                remaining -= take
                proxy.execute_kw(db, uid, pwd, "stock.return.picking.line", "write",
                                 [[line["id"]], {"quantity": take}], {"context": REMOTE_CTX})
            if remaining > 0.0001:
                raise UserError(_("Edbert delivery %(pick)s holds less than %(qty)s to return.",
                                  pick=out["name"], qty=self.qty))
            # `_create_return` is private, and /xmlrpc/2/object refuses a
            # leading underscore: go through the public action, read res_id.
            action = proxy.execute_kw(db, uid, pwd, "stock.return.picking",
                                      "action_create_returns", [[wiz]], {"context": REMOTE_CTX})
            rid = (action or {}).get("res_id")
            if not rid:
                raise UserError(_("Edbert would not create a return for %s.") % out["name"])
            # Marked at once, so a crash after this line is adopted next run.
            proxy.execute_kw(db, uid, pwd, "stock.picking", "write",
                             [[rid], {"origin": self._get_marker()}], {"context": REMOTE_CTX})
            rname = False
        state = proxy.execute_kw(db, uid, pwd, "stock.picking", "read", [[rid]],
                                 {"fields": ["name", "state"]})[0]
        if state["state"] != "done":
            moves = proxy.execute_kw(db, uid, pwd, "stock.move", "search_read",
                                     [[["picking_id", "=", rid]]],
                                     {"fields": ["product_uom_qty"]})
            for m in moves:
                proxy.execute_kw(db, uid, pwd, "stock.move", "write",
                                 [[m["id"]], {"quantity": m["product_uom_qty"], "picked": True}],
                                 {"context": REMOTE_CTX})
            proxy.execute_kw(db, uid, pwd, "stock.picking", "button_validate", [[rid]],
                             {"context": REMOTE_CTX})
            state = proxy.execute_kw(db, uid, pwd, "stock.picking", "read", [[rid]],
                                     {"fields": ["name", "state"]})[0]
        if state["state"] != "done":
            raise UserError(_(
                "The ecom side is returned, but Edbert return %(ret)s came back %(state)s. "
                "Until it is validated the item is in NEITHER warehouse.",
                ret=state["name"], state=state["state"]))
        self.remote_return_name = rname or state["name"]

    def _step_vendor_refund(self):
        """Vendor credit for `qty` of the product, reversed from the posted
        Edbert bill so it carries the same price and the purchase link."""
        if self.vendor_refund_id:
            return
        bills = self.purchase_id.invoice_ids.filtered(
            lambda m: m.move_type == "in_invoice" and m.state == "posted"
            and self.product_id in m.invoice_line_ids.product_id)
        if not bills:
            raise UserError(_("%s has no posted vendor bill to credit.") % self.purchase_id.name)
        bill = bills.sorted("id", reverse=True)[0]
        reversal = self.env["account.move.reversal"].with_context(
            active_model="account.move", active_ids=bill.ids,
        ).create({"reason": self._get_marker(), "journal_id": bill.journal_id.id})
        reversal.reverse_moves()
        refund = reversal.new_move_ids
        refund.ensure_one()
        commands, kept = [], False
        for line in refund.invoice_line_ids:
            if line.display_type == "product" and line.product_id == self.product_id and not kept:
                # `qty` is in the sale line's unit, which is also the
                # purchase line's: the bridge buys in the sale unit.
                pol = self.purchase_id.order_line.filtered(
                    lambda l: l.product_id == self.product_id)[:1]
                qty = pol.product_uom._compute_quantity(self.qty, line.product_uom_id)
                commands.append(Command.update(line.id, {"quantity": qty}))
                kept = True
            else:
                commands.append(Command.delete(line.id))
        refund.write({"invoice_line_ids": commands})
        if not kept:
            raise UserError(_("The vendor credit for %s did not come out as expected.") % bill.name)
        self.vendor_refund_id = refund

    def _step_remote_refund(self):
        """Edbert credit note for `qty`, reversed from Edbert's posted invoice."""
        if self.remote_refund_id:
            return
        proxy, db, uid, pwd = self._remote()
        wid = self._wholesale_id()
        found = proxy.execute_kw(db, uid, pwd, "account.move", "search_read",
                                 [[["move_type", "=", "out_refund"],
                                   ["ref", "ilike", self._get_marker()],
                                   ["state", "!=", "cancel"]]],
                                 {"fields": ["name", "state"]})
        if found:
            # Created by an earlier run that died before it was recorded here.
            # It may also have died before the quantity was cut, so cut it
            # again while it is still a draft. Cutting is idempotent.
            rid, label = found[0]["id"], found[0]["name"]
            draft = found[0]["state"] == "draft"
        else:
            sale = self._remote_sale(proxy, db, uid, pwd)
            invoices = proxy.execute_kw(
                db, uid, pwd, "account.move", "read", [sale["invoice_ids"]],
                {"fields": ["name", "state", "move_type", "journal_id"]}
            ) if sale["invoice_ids"] else []
            invoices = [i for i in invoices
                        if i["move_type"] == "out_invoice" and i["state"] == "posted"]
            if not invoices:
                raise UserError(_("Edbert order %s has no posted invoice to credit.")
                                % sale["name"])
            inv = sorted(invoices, key=lambda i: i["id"], reverse=True)[0]
            ctx = dict(REMOTE_CTX, active_model="account.move", active_ids=[inv["id"]])
            wiz = proxy.execute_kw(db, uid, pwd, "account.move.reversal", "create",
                                   [{"reason": self._get_marker(),
                                     "journal_id": inv["journal_id"][0]}], {"context": ctx})
            action = proxy.execute_kw(db, uid, pwd, "account.move.reversal", "reverse_moves",
                                      [[wiz]], {"context": ctx})
            rid = (action or {}).get("res_id")
            if not rid:
                raise UserError(_("Edbert would not reverse invoice %s.") % inv["name"])
            label, draft = inv["name"], True
        if draft:
            lines = proxy.execute_kw(db, uid, pwd, "account.move.line", "search_read",
                                     [[["move_id", "=", rid], ["display_type", "=", "product"]]],
                                     {"fields": ["product_id"]})
            commands, kept = [], False
            for line in lines:
                pid = line["product_id"][0] if line["product_id"] else False
                if pid == wid and not kept:
                    commands.append([1, line["id"], {"quantity": self.qty}])
                    kept = True
                else:
                    commands.append([2, line["id"]])
            if not kept:
                raise UserError(_("Edbert credit note for %s does not carry this product.")
                                % label)
            proxy.execute_kw(db, uid, pwd, "account.move", "write",
                             [[rid], {"invoice_line_ids": commands}], {"context": REMOTE_CTX})
        name = proxy.execute_kw(db, uid, pwd, "account.move", "read", [[rid]],
                                {"fields": ["name"]})[0]["name"]
        self.write({"remote_refund_id": rid, "remote_refund_name": name})

    def _step_post(self):
        """Post both credits, but only when they agree."""
        proxy, db, uid, pwd = self._remote()
        refund = self.vendor_refund_id
        theirs = proxy.execute_kw(db, uid, pwd, "account.move", "read",
                                  [[self.remote_refund_id]],
                                  {"fields": ["name", "state", "amount_untaxed"]})[0]
        gap = abs(refund.amount_untaxed - theirs["amount_untaxed"])
        if gap > 0.01:
            self.write({"state": "mismatch", "note": _(
                "Edbert credit note %(n)s is %(theirs).2f ex GST but the vendor credit is "
                "%(ours).2f. Neither was posted.",
                n=theirs["name"], theirs=theirs["amount_untaxed"],
                ours=refund.amount_untaxed)})
            self.sale_order_id.message_post(body=self.note)
            return
        if theirs["state"] == "draft":
            proxy.execute_kw(db, uid, pwd, "account.move", "action_post",
                             [[self.remote_refund_id]], {"context": REMOTE_CTX})
            theirs = proxy.execute_kw(db, uid, pwd, "account.move", "read",
                                      [[self.remote_refund_id]],
                                      {"fields": ["name", "state", "amount_untaxed"]})[0]
        if theirs["state"] != "posted":
            raise UserError(_("Edbert credit note %(n)s is %(s)s.",
                              n=theirs["name"], s=theirs["state"]))
        self.remote_refund_name = theirs["name"]
        if refund.state == "draft":
            refund.write({"ref": theirs["name"],
                          "invoice_date": refund.invoice_date or fields.Date.today()})
            refund.action_post()
        if refund.state != "posted":
            raise UserError(_("Vendor credit %(b)s is %(s)s.", b=refund.name, s=refund.state))
        self.write({"state": "done", "note": False})
        self.sale_order_id.message_post(body=_(
            "%(qty)s × %(product)s went back to Edbert: ecom return %(ret)s, Edbert return "
            "%(rret)s, vendor credit %(vc)s, Edbert credit note %(cn)s.",
            qty=self.qty, product=self.product_id.display_name, ret=self.local_return_id.name,
            rret=self.remote_return_name, vc=refund.name, cn=theirs["name"]))
