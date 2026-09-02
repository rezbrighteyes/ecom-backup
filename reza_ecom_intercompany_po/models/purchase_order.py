# -*- coding: utf-8 -*-
"""Make cancelling a bridged purchase order actually undo it.

`d3_external_api` cancels the wholesale sale order by calling `action_cancel`
remotely. Two things on the Edbert databases stop that working, and both leave a
person to finish the job by hand:

1. **Edbert AUTO-LOCKS a confirmed sale order**, and a locked order refuses to
   cancel -- `UserError: You cannot cancel a locked order. Please unlock it
   first.` The connector never unlocks, so the ecom purchase order simply cannot
   be cancelled through the UI.
2. **A validated transfer cannot be un-validated.** Cancelling paperwork does
   not move stock back, so once the bridge has completed the transfer the goods
   sit in the ecom branch's warehouse with nothing recording that they should
   not.

So this returns the stock FIRST, then unlocks, then lets the connector cancel.

ORDER IS DELIBERATE: the ecom receipt is returned BEFORE the wholesale delivery.
Reversing that order would put the goods back into Edbert while ecom still holds
them -- a double count, which is worse than the alternative, because a missing
unit is found at the next stocktake and a duplicated one is not.
"""
import logging
import ssl
import xmlrpc.client

from odoo import _, models
from odoo.exceptions import AccessError, UserError

from .sale_order import RPC_TIMEOUT, _TimeoutTransport

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # ------------------------------------------------------------------ hooks
    def button_cancel(self):
        """Cancel, having first said something useful if it cannot be.

        Odoo REFUSES to cancel a purchase order whose receipt is done -- core
        `purchase.order.button_cancel` raises "since they have receipts that are
        already done". So returning the goods here would move real stock and
        then still fail, which is the worst of both. The goods go back through
        the explicit Return to Edbert button instead; this only makes the
        refusal say so.
        """
        blocked = self.filtered(
            lambda p: p.external_api and p.external_api_sale
            and any(pick.state == "done" for pick in p.picking_ids))
        if blocked:
            raise UserError(_(
                "%s has already been received, so Odoo will not cancel it. Press "
                "\"Return to Edbert\" to send the goods back -- that reverses the "
                "transfer on both sides and leaves nothing received."
            ) % ", ".join(blocked.mapped("name")))
        return super().button_cancel()

    # ---------------------------------------------------------- public action
    def action_reza_return_to_edbert(self):
        """Send a completed bridge transfer back, both sides.

        Public because Odoo refuses a private method over
        `/web/dataset/call_button`, and the group is re-tested here because
        `groups=` on a view button hides it without stopping an RPC caller.
        """
        if not self.env.user.has_group("purchase.group_purchase_user"):
            raise AccessError(_("Only Purchase users can return goods to Edbert."))
        for order in self:
            order._reza_return_bridged_stock()
        return True

    def cancel_external_api_sale(self):
        """Unlock the wholesale order so the connector's cancel can land."""
        for order in self.filtered("external_api_sale"):
            order._reza_unlock_remote_sale()
        return super().cancel_external_api_sale()

    # ------------------------------------------------------------ wholesale IO
    def _reza_remote(self):
        """(execute_kw proxy, db, uid, password) for wholesale, or None."""
        self.ensure_one()
        api = self.company_id.sudo()
        url, db = api.external_api_url, api.external_api_db
        user, pwd = api.external_api_username, api.external_api_password
        if not (url and db and user and pwd):
            return None
        if not url.lower().startswith("https://"):
            raise UserError(_("The wholesale API address on %s must start with https://.")
                            % api.name)
        ctx = ssl.create_default_context()
        try:
            common = xmlrpc.client.ServerProxy(
                "%s/xmlrpc/2/common" % url,
                transport=_TimeoutTransport(RPC_TIMEOUT, context=ctx))
            uid = common.authenticate(db, user, pwd, {})
        except Exception as exc:  # noqa: BLE001
            # Deliberately FAILS CLOSED. Cancelling without knowing whether
            # wholesale has already shipped would leave the goods sitting in
            # its customer location with nothing recording them.
            _logger.exception("reza_ecom_intercompany_po: wholesale unreachable for %s",
                              self.name)
            raise UserError(_(
                "The wholesale system could not be reached, so it is not possible to tell "
                "whether these goods have already been sent. Try again once it responds, "
                "rather than cancelling blind.")) from exc
        if not uid:
            raise UserError(_("Could not sign in to the wholesale system."))
        proxy = xmlrpc.client.ServerProxy(
            "%s/xmlrpc/2/object" % url, transport=_TimeoutTransport(RPC_TIMEOUT, context=ctx))
        return proxy, db, uid, pwd

    def _reza_unlock_remote_sale(self):
        """Clear `locked` on the wholesale sale order. Idempotent and quiet.

        `skip_reza_fuel_surcharge_sync` and `skip_tax_update` are both required:
        any write to a sale order on that database re-enters the Starshipit
        surcharge sync (the documented RecursionError path) and the Xero
        connector's `_auto_set_tax_state`, which would silently restate
        `tax_state` on a live order.
        """
        self.ensure_one()
        remote = self._reza_remote()
        if not remote:
            return False
        proxy, db, uid, pwd = remote
        sid = self.external_api_sale
        rows = proxy.execute_kw(db, uid, pwd, "sale.order", "search_read",
                                [[["id", "=", sid]]], {"fields": ["name", "state", "locked"]})
        if not rows:
            # Already gone. Leave it: the connector will raise its own clear
            # "Record does not exist" rather than us guessing what happened.
            return False
        if not rows[0].get("locked"):
            return False
        proxy.execute_kw(db, uid, pwd, "sale.order", "write", [[sid], {"locked": False}],
                         {"context": {"skip_reza_fuel_surcharge_sync": True,
                                      "skip_tax_update": True}})
        _logger.info("reza_ecom_intercompany_po: unlocked wholesale %s for %s",
                     rows[0]["name"], self.name)
        return True

    # --------------------------------------------------------------- the stock
    def _reza_return_bridged_stock(self):
        """Reverse a completed transfer, both sides, or refuse and say why."""
        self.ensure_one()
        local_done = self.picking_ids.filtered(lambda p: p.state == "done")
        remote = self._reza_remote()
        remote_done = []
        if remote:
            proxy, db, uid, pwd = remote
            rows = proxy.execute_kw(db, uid, pwd, "sale.order", "search_read",
                                    [[["id", "=", self.external_api_sale]]],
                                    {"fields": ["name", "picking_ids", "invoice_ids"]})
            if rows:
                if rows[0].get("invoice_ids"):
                    raise UserError(_(
                        "Wholesale order %s has been invoiced, so the goods cannot simply be "
                        "sent back. Raise a credit note there first, then cancel this.")
                        % rows[0]["name"])
                if rows[0].get("picking_ids"):
                    remote_done = [
                        p for p in proxy.execute_kw(
                            db, uid, pwd, "stock.picking", "read", [rows[0]["picking_ids"]],
                            {"fields": ["name", "state", "picking_type_code"]})
                        if p["state"] == "done"
                    ]
        if not local_done and not remote_done:
            # Say so. The button is reachable before anything has shipped, and
            # doing nothing quietly reads as a broken button.
            raise UserError(_(
                "Nothing has been received for %s yet, so there is nothing to send back. "
                "Cancel it instead.") % self.name)

        if self.invoice_ids:
            raise UserError(_(
                "%s has been billed, so the goods cannot simply be sent back. Reverse the "
                "bill first, then cancel this.") % self.name)

        # ecom first -- see the module docstring on why this order matters.
        for picking in local_done:
            self._reza_return_local(picking)
        for p in remote_done:
            self._reza_return_remote(p["id"], p["name"])
        return True

    def _reza_return_local(self, picking):
        """Return an ecom receipt: the goods leave the branch warehouse again."""
        self.ensure_one()
        wizard = self.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking",
        ).create({"picking_id": picking.id})
        if not wizard.product_return_moves:
            raise UserError(_("Nothing to return on %s.") % picking.name)
        # The wizard's lines arrive at quantity ZERO unless a user types into
        # them, and `_create_return` then raises "Please specify at least one
        # non-zero quantity". `move_quantity` is what the picking actually
        # moved, which is exactly what we are sending back.
        for line in wizard.product_return_moves:
            line.quantity = line.move_quantity
        # `_create_return` returns the picking itself and already runs
        # action_confirm + action_assign. In-process, so the private name is
        # reachable here -- it is NOT over RPC, see _reza_return_remote.
        returns = wizard._create_return()
        for ret in returns:
            for move in ret.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            ret.with_context(skip_backorder=True).button_validate()
            if ret.state != "done":
                raise UserError(_("Could not return %s -- %s came back %s. Sort the stock "
                                  "out by hand, then cancel.")
                                % (picking.name, ret.name, ret.state))
            _logger.info("reza_ecom_intercompany_po: returned ecom %s via %s",
                         picking.name, ret.name)

    def _reza_return_remote(self, picking_id, picking_name):
        """Return a wholesale delivery: the goods go back into Edbert's stock."""
        self.ensure_one()
        proxy, db, uid, pwd = self._reza_remote()
        # reza_skip_auto_invoice_prompt: the Edbert dispatch module intercepts
        # button_validate on a customer document and hands back a wizard instead
        # of validating. Without this the return is created and never completes.
        ctx = {"skip_reza_fuel_surcharge_sync": True, "skip_tax_update": True,
               "reza_skip_auto_invoice_prompt": True, "skip_backorder": True}
        wid = proxy.execute_kw(db, uid, pwd, "stock.return.picking", "create",
                               [{"picking_id": picking_id}],
                               {"context": dict(ctx, active_id=picking_id,
                                                active_model="stock.picking")})
        # `_create_return` is private and `/xmlrpc/2/object` refuses a leading
        # underscore, so go through the public action and read `res_id` out of
        # the action dict it hands back.
        action = proxy.execute_kw(db, uid, pwd, "stock.return.picking",
                                  "action_create_returns", [[wid]], {"context": ctx})
        rid = (action or {}).get("res_id")
        if not rid:
            raise UserError(_("Wholesale would not create a return for %s.") % picking_name)
        for rid in [rid]:
            moves = proxy.execute_kw(db, uid, pwd, "stock.move", "search_read",
                                     [[["picking_id", "=", rid]]],
                                     {"fields": ["product_uom_qty"]})
            for m in moves:
                proxy.execute_kw(db, uid, pwd, "stock.move", "write",
                                 [[m["id"]], {"quantity": m["product_uom_qty"],
                                              "picked": True}], {"context": ctx})
            proxy.execute_kw(db, uid, pwd, "stock.picking", "button_validate",
                             [[rid]], {"context": ctx})
            state = proxy.execute_kw(db, uid, pwd, "stock.picking", "read",
                                     [[rid], ["name", "state"]], {"context": ctx})[0]
            if state["state"] != "done":
                raise UserError(_(
                    "The ecom side has already been returned, but wholesale return %s came "
                    "back %s. The goods are recorded in NEITHER warehouse until somebody "
                    "validates it.") % (state["name"], state["state"]))
            _logger.info("reza_ecom_intercompany_po: returned wholesale %s via %s",
                         picking_name, state["name"])
