import base64
import hashlib
import json
import secrets
import urllib.parse
from datetime import date

from odoo import _, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request, route

from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.rma.controllers.main import PortalRma


class RezaRmaPortal(PortalRma):

    def _prepare_portal_counter_values(self, counter):
        # Odoo 20: /my/counters asks each controller for (model, domain,
        # access); "sudo" keeps the old sudo().search_count().
        if counter == "reza_rma_count":
            return "reza.rma.request", self._reza_get_request_domain(), "sudo"
        return super()._prepare_portal_counter_values(counter)

    def _reza_get_request_domain(self):
        partner = request.env.user.partner_id.commercial_partner_id
        domain = [("partner_id", "child_of", partner.id)]
        if request.env.website:
            domain.extend(
                [
                    ("website_id", "=", request.env.website.id),
                    ("company_id", "=", request.env.website.company_id.id),
                ]
            )
        return domain

    def _reza_get_rma_domain(self):
        partner = request.env.user.partner_id.commercial_partner_id
        domain = [
            ("partner_id", "child_of", partner.id),
            ("reza_portal_visible", "=", True),
        ]
        if request.env.website:
            domain.append(("company_id", "=", request.env.website.company_id.id))
        return domain

    def _reza_get_rma_or_raise(self, rma_id):
        rma = request.env["rma"].sudo().browse(rma_id)
        if not rma.exists():
            raise AccessError(_("Record not found."))
        partner = request.env.user.partner_id.commercial_partner_id
        if rma.partner_id.commercial_partner_id.id != partner.id:
            raise AccessError(_("Access denied."))
        if request.env.website:
            if rma.company_id.id != request.env.website.company_id.id:
                raise AccessError(_("Access denied."))
        return rma

    def _reza_get_eligible_orders(self, partner):
        domain = [
            ("partner_id", "child_of", partner.id),
            ("state", "in", ["sale", "done"]),
        ]
        if request.env.website:
            domain.append(("website_id", "=", request.env.website.id))
        all_orders = request.env["sale.order"].sudo().search(domain, order="id desc")
        return all_orders.filtered(
            lambda o: o.date_order
            and o.company_id.reza_get_rma_return_deadline(o.date_order.date()) >= date.today()
        )

    def _reza_render_create_form(self, partner, error=None, selected_order_id=None):
        eligible_orders = self._reza_get_eligible_orders(partner)
        reasons = request.env["reza.rma.reason"].sudo().search(
            [("customer_selectable", "=", True), ("active", "=", True)],
            order="sequence, name",
        )
        order_deadlines = {
            order.id: order.company_id.reza_get_rma_return_deadline(order.date_order.date())
            for order in eligible_orders
            if order.date_order
        }
        company = request.env.website.company_id if request.env.website else request.env.company
        return request.render("reza_rma.portal_rma_create", {
            "eligible_orders": eligible_orders,
            "reasons": reasons,
            "page_name": "rma_return",
            "error": error or {},
            "selected_order_id": selected_order_id,
            "order_deadlines": order_deadlines,
            "return_window_days": company.reza_rma_return_window_days,
            "disclaimer_text": company.reza_rma_disclaimer_text,
            "return_shipping_fee": company.reza_rma_return_shipping_fee,
            "submission_token": secrets.token_urlsafe(24),
        })

    def _reza_get_line_delivery_move(self, line):
        moves = line.move_ids.filtered(
            lambda m: m.state == "done"
            and m.picking_id
            and m.picking_id.state == "done"
            and m.picking_id.picking_type_id.code == "outgoing"
        )
        return moves.sorted(key=lambda m: (m.picking_id.date_done or m.date or m.create_date), reverse=True)[:1]

    def _reza_get_remaining_quantity(self, line):
        requested = sum(request.env["reza.rma.request.line"].sudo().search([
            ("sale_order_line_id", "=", line.id),
            ("request_id.state", "not in", ["cancelled"]),
        ]).mapped("quantity"))
        legacy = request.env["rma"].sudo().search([
            ("sale_line_id", "=", line.id),
            ("reza_request_line_id", "=", False),
            ("state", "not in", ["cancelled"]),
        ])
        requested += sum(legacy.mapped("product_uom_qty"))
        return max((line.qty_delivered or 0.0) - requested, 0.0)

    def _reza_get_request_by_token(self, token):
        domain = [("portal_access_token", "=", token)]
        if request.env.website:
            domain.extend([
                ("website_id", "=", request.env.website.id),
                ("company_id", "=", request.env.website.company_id.id),
            ])
        return request.env["reza.rma.request"].sudo().search(domain, limit=1)

    def _reza_hash_guest_value(self, value):
        secret = request.env["ir.config_parameter"].sudo().get_str(
            "database.secret", "reza-rma"
        )
        return hashlib.sha256(f"{secret}:{value}".encode()).hexdigest()

    def _reza_get_ip_hash(self):
        forwarded = request.httprequest.headers.get("X-Forwarded-For", "")
        ip = forwarded.split(",")[0].strip() or request.httprequest.remote_addr or ""
        return self._reza_hash_guest_value(ip)

    def _reza_check_and_record_lookup(self, order_number, email, successful=False):
        Attempt = request.env["reza.rma.lookup.attempt"].sudo()
        ip_hash = self._reza_get_ip_hash()
        lookup_hash = self._reza_hash_guest_value(
            f"{order_number.strip().lower()}:{email.strip().lower()}"
        )
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), minutes=15)
        attempts = Attempt.search_count(
            [
                ("website_id", "=", request.env.website.id),
                ("create_date", ">=", cutoff),
                "|",
                ("ip_hash", "=", ip_hash),
                ("lookup_hash", "=", lookup_hash),
            ]
        )
        if attempts >= 5:
            return False
        Attempt.create(
            {
                "ip_hash": ip_hash,
                "lookup_hash": lookup_hash,
                "website_id": request.env.website.id,
                "successful": successful,
            }
        )
        return True

    def _reza_create_grouped_request(
        self, order, selections, operation_type, return_method="auspost", idempotency_seed=None
    ):
        resolution_map = {
            "credit_note": "refund",
            "store_credit": "store_credit",
            "exchange": "exchange",
        }
        payload = [
            {
                "line_id": item["line"].id,
                "quantity": item["quantity"],
                "reason_id": item["reason"].id,
            }
            for item in selections
        ]
        idempotency_key = hashlib.sha256(
            json.dumps(
                {
                    "seed": idempotency_seed or secrets.token_hex(16),
                    "order_id": order.id,
                    "operation_type": operation_type,
                    "items": payload,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        existing = request.env["reza.rma.request"].sudo().search(
            [("idempotency_key", "=", idempotency_key)], limit=1
        )
        if existing:
            return existing
        request.env.cr.execute(
            "SELECT id FROM sale_order_line WHERE id IN %s FOR UPDATE",
            [tuple(item["line"].ids[0] for item in selections)],
        )
        for item in selections:
            if item["quantity"] <= 0 or item["quantity"] > self._reza_get_remaining_quantity(item["line"]):
                raise ValidationError(
                    _("A selected return quantity is no longer available. Refresh and try again.")
                )
            allowed_resolution = item["reason"].allowed_resolution
            if allowed_resolution not in ("any", resolution_map[operation_type]):
                raise ValidationError(
                    _("The selected return reason does not allow this resolution.")
                )
        website = order.website_id or request.env.website
        if not website or website.company_id != order.company_id:
            raise ValidationError(_("The order is not linked to a valid return website."))
        all_fees_waived = all(item["reason"].reza_return_fee_waived for item in selections)
        return_fee = 0.0 if all_fees_waived else order.company_id.reza_rma_return_shipping_fee
        operation = (
            order.company_id.reza_rma_exchange_operation_id
            if operation_type == "exchange"
            else order.company_id.reza_rma_refund_operation_id
        )
        if not operation:
            raise ValidationError(
                _("Returns are temporarily unavailable because the required RMA operation is not configured.")
            )
        if (
            operation.action_create_refund
            in ("automatic_on_confirm", "automatic_after_receipt", "update_quantity")
            or operation.action_create_delivery
            in ("automatic_on_confirm", "automatic_after_receipt")
            or operation.auto_confirm_reception
        ):
            raise ValidationError(
                _("The customer return operation cannot automatically refund, replace, or validate receipt.")
            )
        if operation_type == "exchange" and operation.action_create_delivery != "manual_after_receipt":
            raise ValidationError(
                _("The exchange RMA operation must create replacement delivery manually after receipt.")
            )
        if operation_type != "exchange" and operation.action_create_refund != "manual_after_receipt":
            raise ValidationError(
                _("The refund/store-credit RMA operation must create refunds manually after receipt.")
            )
        req = request.env["reza.rma.request"].sudo().create(
            {
                "company_id": order.company_id.id,
                "website_id": website.id,
                "partner_id": order.partner_id.id,
                "sale_order_id": order.id,
                "idempotency_key": idempotency_key,
                "policy_version": "1",
                "policy_text_snapshot": order.company_id.reza_rma_disclaimer_text or _("Returns policy"),
                "policy_accepted_at": fields.Datetime.now(),
                "policy_accepted_ip_hash": self._reza_get_ip_hash(),
                "currency_id": order.currency_id.id,
                "return_shipping_fee": return_fee,
                "label_state": (
                    "pending"
                    if order.company_id.reza_rma_enable_labels and return_method == "auspost"
                    else "manual"
                ),
            }
        )
        for item in selections:
            line = item["line"]
            move = self._reza_get_line_delivery_move(line)
            quantity = item["quantity"]
            item_untaxed = order.currency_id.round(
                (line.price_subtotal / line.product_uom_qty) * quantity
            ) if line.product_uom_qty else 0.0
            item_total = order.currency_id.round(
                (line.price_total / line.product_uom_qty) * quantity
            ) if line.product_uom_qty else item_untaxed
            expected_resolution_amount = 0.0 if item["reason"].code == "WARRANTY" else item_total
            rma = request.env["rma"].sudo().create(
                {
                    "partner_id": order.partner_id.id,
                    "order_id": order.id,
                    "picking_id": move.picking_id.id if move else False,
                    "move_id": move.id if move else False,
                    "product_id": line.product_id.id,
                    "product_uom_qty": quantity,
                    "product_uom": line.product_uom_id.id,
                    "company_id": order.company_id.id,
                    "operation_id": operation.id,
                    "reza_reason_id": item["reason"].id,
                    "reza_operation_type": operation_type,
                    "reza_return_method": return_method,
                    "reza_customer_notes": item.get("notes"),
                    "reza_disclaimer_accepted": True,
                    "reza_return_shipping_fee": return_fee,
                    "reza_portal_visible": True,
                }
            )
            rma.product_uom_qty = quantity
            request_line = request.env["reza.rma.request.line"].sudo().create(
                {
                    "request_id": req.id,
                    "rma_id": rma.id,
                    "sale_order_line_id": line.id,
                    "source_move_id": move.id if move else False,
                    "product_id": line.product_id.id,
                    "uom_id": line.product_uom_id.id,
                    "quantity": quantity,
                    "reason_id": item["reason"].id,
                    "resolution": resolution_map[operation_type],
                    "item_untaxed": item_untaxed,
                    "item_tax": item_total - item_untaxed,
                    "item_total": item_total,
                    "expected_resolution_amount": expected_resolution_amount,
                    "resolution_idempotency_key": f"{idempotency_key}:{line.id}",
                }
            )
            rma.reza_request_line_id = request_line
        req.rma_ids.filtered(lambda rma: rma.state == "draft").action_confirm()
        req.receipt_picking_id = req.rma_ids[:1].reception_move_id.picking_id
        if req.line_ids:
            fee_share = order.currency_id.round(return_fee / len(req.line_ids))
            req.line_ids.write({"shipping_fee_share": fee_share})
        if order.company_id.reza_rma_enable_labels and return_method == "auspost":
            req.action_retry_label()
        return req

    # ── Guest / public returns flow ──────────────────────────────────────────

    def _reza_lookup_order_by_number_and_email(self, order_number, email):
        """Find an eligible sale order by order name and partner email."""
        domain = [
            ("name", "=", order_number),
            ("state", "in", ["sale", "done"]),
        ]
        if request.env.website:
            domain.append(("website_id", "=", request.env.website.id))

        orders = request.env["sale.order"].sudo().search(domain, limit=20)
        email_lower = email.strip().lower()

        for order in orders:
            partner_emails = set()
            for p in (
                order.partner_id,
                order.partner_id.commercial_partner_id,
                order.partner_invoice_id,
            ):
                if p and p.email:
                    partner_emails.add(p.email.strip().lower())

            if email_lower not in partner_emails:
                continue

            if not order.date_order:
                continue
            deadline = order.company_id.reza_get_rma_return_deadline(order.date_order.date())
            if date.today() > deadline:
                continue
            return order

        return None

    def _reza_get_guest_return_lines(self, order):
        """Return serialisable line dicts for the guest return form."""
        lines = []
        for line in order.order_line:
            if not line.product_id:
                continue
            if line.product_id.type == "service":
                continue
            product_tmpl = line.product_id.product_tmpl_id
            max_qty = self._reza_get_remaining_quantity(line)
            lines.append({
                "id": line.id,
                "product_id": line.product_id.id,
                "product_name": line.product_id.name,
                "qty": line.product_uom_qty,
                "qty_delivered": line.qty_delivered,
                "max_qty": max_qty,
                "price_subtotal": line.price_subtotal,
                "currency_symbol": order.currency_id.symbol,
                "uom": line.product_uom_id.name if line.product_uom_id else "",
                "already_returned": max_qty <= 0,
                "returnable": not product_tmpl.reza_non_returnable and max_qty > 0,
                "return_policy_note": product_tmpl.reza_return_policy_note or "",
            })
        return lines

    @route("/returns", type="http", auth="public", website=True)
    def portal_guest_returns(self, **kwargs):
        return request.render("reza_rma.portal_guest_returns_lookup", {
            "error": {},
            "order_number": "",
            "email": "",
        })

    @route("/returns/find", type="http", auth="public", website=True, methods=["POST"])
    def portal_guest_returns_find(self, **post):
        error = {}
        order_number = post.get("order_number", "").strip()
        email = post.get("email", "").strip()

        if not order_number:
            error["order_number"] = _("Please enter your order number.")
        if not email:
            error["email"] = _("Please enter your email address.")

        if not error:
            allowed = self._reza_check_and_record_lookup(order_number, email)
            order = (
                self._reza_lookup_order_by_number_and_email(order_number, email)
                if allowed
                else None
            )
            if not order:
                error["order_number"] = _(
                    "We couldn't find an order matching that number and email. "
                    "Please check your details and try again."
                )
            else:
                request.env["reza.rma.lookup.attempt"].sudo().search(
                    [
                        ("website_id", "=", request.env.website.id),
                        ("lookup_hash", "=", self._reza_hash_guest_value(
                            f"{order_number.strip().lower()}:{email.strip().lower()}"
                        )),
                    ],
                    order="id desc",
                    limit=1,
                ).successful = True

        if error:
            return request.render("reza_rma.portal_guest_returns_lookup", {
                "error": error,
                "order_number": order_number,
                "email": email,
            })

        lines = self._reza_get_guest_return_lines(order)
        if all(l["already_returned"] or not l["returnable"] for l in lines):
            message = _(
                "There are no delivered items available to return on this order yet. "
                "Please contact us if you need further assistance."
            )
            if any(l["qty_delivered"] > 0 for l in lines):
                message = _(
                    "All returnable items in this order have already been returned. "
                    "Please contact us if you need further assistance."
                )
            return request.render("reza_rma.portal_guest_returns_lookup", {
                "error": {"order_number": message},
                "order_number": order_number,
                "email": email,
            })

        reasons = request.env["reza.rma.reason"].sudo().search(
            [("customer_selectable", "=", True), ("active", "=", True)],
            order="sequence, name",
        )
        company = order.company_id
        deadline = company.reza_get_rma_return_deadline(order.date_order.date())
        continuation_token = secrets.token_urlsafe(24)
        request.session["reza_return_lookup"] = {
            "token": continuation_token,
            "order_id": order.id,
        }

        return request.render("reza_rma.portal_guest_returns_form", {
            "order": order,
            "lines": lines,
            "reasons": reasons,
            "deadline": deadline,
            "email": email,
            "disclaimer_text": company.reza_rma_disclaimer_text,
            "return_shipping_fee": company.reza_rma_return_shipping_fee,
            "bonus_percent": company.reza_rma_store_credit_bonus_percent,
            "currency_symbol": order.currency_id.symbol,
            "error": {},
            "post": {},
            "continuation_token": continuation_token,
        })

    @route("/returns/submit", type="http", auth="public", website=True, methods=["POST"])
    def portal_guest_returns_submit(self, **post):
        error = {}

        lookup = request.session.get("reza_return_lookup", {})
        continuation_token = post.get("continuation_token", "")
        order = request.env["sale.order"].sudo().browse(lookup.get("order_id", 0))
        if (
            not order.exists()
            or not continuation_token
            or lookup.get("token") != continuation_token
            or (request.env.website and order.website_id != request.env.website)
        ):
            return request.redirect("/returns")

        company = order.company_id

        # Validate lines
        raw_line_ids = request.httprequest.form.getlist("line_ids")
        if not raw_line_ids:
            error["lines"] = _("Please select at least one item to return.")

        valid_line_ids = []
        if not error.get("lines"):
            for lid_str in raw_line_ids:
                try:
                    lid = int(lid_str)
                except (ValueError, TypeError):
                    continue
                line = request.env["sale.order.line"].sudo().browse(lid)
                if (
                    line.exists()
                    and line.order_id.id == order.id
                    and line.product_id.type != "service"
                    and not line.product_id.product_tmpl_id.reza_non_returnable
                    and self._reza_get_remaining_quantity(line) > 0
                ):
                    valid_line_ids.append(lid)
            if not valid_line_ids:
                error["lines"] = _("No valid returnable items were selected.")

        # Per-item reasons (reason_id_{lid} from the YETI-style wizard)
        # Fall back to a shared reza_reason_id if the old single-reason form is used.
        item_reasons = {}
        for lid in valid_line_ids:
            try:
                r_id = int(post.get(f"reason_id_{lid}", 0) or post.get("reza_reason_id", 0))
            except (ValueError, TypeError):
                r_id = 0
            reason = request.env["reza.rma.reason"].sudo().browse(r_id)
            if not reason.exists() or not reason.customer_selectable:
                error["reza_reason_id"] = _("Please select a return reason for each item.")
                break
            item_reasons[lid] = reason

        # Validate outcome
        operation_type = post.get("reza_operation_type")
        if operation_type not in ("credit_note", "store_credit", "exchange"):
            error["reza_operation_type"] = _("Please select a return outcome.")

        # Validate disclaimer
        if not post.get("reza_disclaimer_accepted"):
            error["disclaimer"] = _("You must accept the returns policy to proceed.")

        if error:
            lines = self._reza_get_guest_return_lines(order)
            reasons = request.env["reza.rma.reason"].sudo().search(
                [("customer_selectable", "=", True), ("active", "=", True)],
                order="sequence, name",
            )
            deadline = company.reza_get_rma_return_deadline(order.date_order.date())
            return request.render("reza_rma.portal_guest_returns_form", {
                "order": order,
                "lines": lines,
                "reasons": reasons,
                "deadline": deadline,
                "email": "",
                "disclaimer_text": company.reza_rma_disclaimer_text,
                "return_shipping_fee": company.reza_rma_return_shipping_fee,
                "bonus_percent": company.reza_rma_store_credit_bonus_percent,
                "currency_symbol": order.currency_id.symbol,
                "error": error,
                "post": post,
                "continuation_token": continuation_token,
            })

        selections = []
        for lid in valid_line_ids:
            line = request.env["sale.order.line"].sudo().browse(lid)
            qty_raw = post.get(f"qty_{lid}", "")
            try:
                qty = float(qty_raw) if qty_raw else self._reza_get_remaining_quantity(line)
            except (ValueError, TypeError):
                qty = 0.0
            remaining = self._reza_get_remaining_quantity(line)
            if qty <= 0 or qty > remaining:
                return request.redirect("/returns")
            selections.append(
                {
                    "line": line,
                    "quantity": qty,
                    "reason": item_reasons[lid],
                    "notes": post.get(f"notes_{lid}", "").strip()
                    or post.get("reza_customer_notes", "").strip(),
                }
            )

        # If the return fee must be collected upfront (exchange has no refund to deduct from)
        all_fees_waived = all(r.reza_return_fee_waived for r in item_reasons.values())
        return_fee = 0.0 if all_fees_waived else float(company.reza_rma_return_shipping_fee)
        if return_fee > 0.0 and operation_type == "exchange":
            pending = request.env["reza.rma.pending.submission"].sudo().create({
                "sale_order_id": order.id,
                "submission_json": json.dumps({
                    "order_id": order.id,
                    "continuation_token": continuation_token,
                    "operation_type": operation_type,
                    "exchange_preference": post.get("reza_exchange_preference", "").strip(),
                    "lines": [
                        {
                            "line_id": lid,
                            "reason_id": item_reasons[lid].id,
                            "qty": float(
                                post.get(f"qty_{lid}") or
                                self._reza_get_remaining_quantity(
                                    request.env["sale.order.line"].sudo().browse(lid)
                                )
                            ),
                            "notes": (
                                post.get(f"notes_{lid}", "") or
                                post.get("reza_customer_notes", "")
                            ).strip(),
                        }
                        for lid in valid_line_ids
                    ],
                }),
                "amount": return_fee,
                "currency_id": order.currency_id.id,
            })
            request.session.pop("reza_return_lookup", None)
            return request.redirect(f"/returns/pay/{pending.token}")

        grouped_request = self._reza_create_grouped_request(
            order,
            selections,
            operation_type,
            idempotency_seed=continuation_token,
        )
        request.session.pop("reza_return_lookup", None)
        for rma in grouped_request.rma_ids:
            rma.reza_send_submitted_email()
        return request.redirect(
            f"/returns/confirmation?token={urllib.parse.quote(grouped_request.portal_access_token)}"
        )

    @route("/returns/confirmation", type="http", auth="public", website=True)
    def portal_guest_returns_confirmation(self, token=None, **kwargs):
        grouped_request = self._reza_get_request_by_token(token) if token else False
        if not grouped_request:
            return request.redirect("/returns")
        return request.render("reza_rma.portal_guest_returns_confirmation", {
            "rma_refs": [grouped_request.name],
            "grouped_request": grouped_request,
            "token": grouped_request.portal_access_token,
        })

    # ── Return postage payment ───────────────────────────────────────────────

    @route("/returns/pay/<string:token>", type="http", auth="public", website=True)
    def portal_guest_returns_pay(self, token, **kwargs):
        from odoo.addons.payment import utils as payment_utils

        pending = request.env["reza.rma.pending.submission"].sudo().search(
            [("token", "=", token), ("state", "=", "pending")], limit=1
        )
        if not pending:
            return request.redirect("/returns")

        order = pending.sale_order_id
        amount = pending.amount
        currency = pending.currency_id
        partner_id = order.partner_id.id
        company_id = order.company_id.id

        # Odoo 20 renamed the payment availability API: _get_compatible_* is
        # now provider._find_available_providers / _find_available_payment_methods
        # / _find_available_tokens (same calls as PaymentPortal._prepare_payment_form_values).
        providers_sudo = request.env["payment.provider"].sudo()._find_available_providers(
            company_id,
            partner_id,
            amount,
            currency_id=currency.id,
        )
        payment_methods_sudo = providers_sudo._find_available_payment_methods(
            partner_id,
            currency_id=currency.id,
        )._deduplicate_by_code()
        tokens_sudo = providers_sudo._find_available_tokens(partner_id)
        show_tokenize_input_mapping = {
            provider.id: provider.allow_tokenization
            and not provider._is_tokenization_required()
            for provider in providers_sudo
        }

        access_token = payment_utils.generate_access_token(partner_id, amount, currency.id)

        return request.render("reza_rma.portal_guest_returns_pay_page", {
            "pending": pending,
            "amount": amount,
            "currency": currency,
            "currency_id": currency.id,
            "partner_id": partner_id,
            "reference_prefix": pending.payment_reference,
            "providers_sudo": providers_sudo,
            "providers": providers_sudo,
            "payment_methods_sudo": payment_methods_sudo,
            "payment_methods": payment_methods_sudo,
            "tokens_sudo": tokens_sudo,
            "tokens": tokens_sudo,
            "default_token_id": None,
            "show_tokenize_input_mapping": show_tokenize_input_mapping,
            "access_token": access_token,
            "transaction_route": "/payment/transaction",
            "landing_route": f"/returns/pay/{token}/done",
        })

    @route("/returns/pay/<string:token>/done", type="http", auth="public", website=True)
    def portal_guest_returns_pay_done(self, token, **kwargs):
        pending = request.env["reza.rma.pending.submission"].sudo().search(
            [("token", "=", token), ("state", "=", "pending")], limit=1
        )
        if not pending:
            return request.redirect("/returns")

        tx = request.env["payment.transaction"].sudo().search(
            [
                ("reference", "=", pending.payment_reference),
                ("state", "in", ("done", "authorized")),
            ],
            limit=1,
        )
        if not tx:
            return request.redirect(f"/returns/pay/{token}?error=1")

        data = pending.get_submission_data()
        order = request.env["sale.order"].sudo().browse(data["order_id"])
        if not order.exists():
            return request.redirect("/returns")

        selections = []
        for item in data["lines"]:
            line = request.env["sale.order.line"].sudo().browse(item["line_id"])
            reason = request.env["reza.rma.reason"].sudo().browse(item["reason_id"])
            selections.append({
                "line": line,
                "quantity": item["qty"],
                "reason": reason,
                "notes": item.get("notes", ""),
            })

        grouped_request = self._reza_create_grouped_request(
            order,
            selections,
            data["operation_type"],
            idempotency_seed=data["continuation_token"],
        )
        pending.write({"state": "done"})
        for rma in grouped_request.rma_ids:
            rma.reza_send_submitted_email()
        return request.redirect(
            f"/returns/confirmation?token={urllib.parse.quote(grouped_request.portal_access_token)}"
        )

    # ── Guest return tracking ────────────────────────────────────────────────

    def _reza_lookup_request_by_ref_and_email(self, ref, email):
        grouped_request = request.env["reza.rma.request"].sudo().search(
            [("name", "=", ref.strip())], limit=1
        )
        if not grouped_request:
            return None
        if request.env.website and (
            grouped_request.website_id != request.env.website
            or grouped_request.company_id != request.env.website.company_id
        ):
            return None
        email_lower = email.strip().lower()
        partner_emails = {
            partner.email.strip().lower()
            for partner in (
                grouped_request.partner_id,
                grouped_request.partner_id.commercial_partner_id,
            )
            if partner and partner.email
        }
        return grouped_request if email_lower in partner_emails else None

    @route("/returns/track", type="http", auth="public", website=True)
    def portal_guest_track_lookup(self, **kwargs):
        return request.render("reza_rma.portal_guest_track_lookup", {
            "error": {},
            "ref": "",
            "email": "",
        })

    @route("/returns/track/find", type="http", auth="public", website=True, methods=["POST"])
    def portal_guest_track_find(self, **post):
        error = {}
        ref = post.get("ref", "").strip()
        email = post.get("email", "").strip()
        if not ref:
            error["ref"] = _("Please enter your return reference number.")
        if not email:
            error["email"] = _("Please enter your email address.")
        if not error:
            allowed = self._reza_check_and_record_lookup(ref, email)
            grouped_request = (
                self._reza_lookup_request_by_ref_and_email(ref, email)
                if allowed
                else None
            )
            if not grouped_request:
                error["ref"] = _("No return found matching that reference and email.")
        if error:
            return request.render("reza_rma.portal_guest_track_lookup", {
                "error": error,
                "ref": ref,
                "email": email,
            })
        return request.redirect(
            f"/returns/request/{urllib.parse.quote(grouped_request.portal_access_token)}"
        )

    @route("/returns/request/<string:token>", type="http", auth="public", website=True)
    def portal_guest_track_detail(self, token, **kwargs):
        grouped_request = self._reza_get_request_by_token(token)
        if not grouped_request:
            return request.redirect("/returns/track")
        return request.render("reza_rma.portal_guest_track_detail", {
            "rma": grouped_request.rma_ids[:1],
            "grouped_request": grouped_request,
            "token": token,
            "ref": grouped_request.name,
        })

    @route("/returns/request/<string:token>/message", type="http", auth="public", website=True, methods=["POST"])
    def portal_guest_track_message(self, token, **post):
        grouped_request = self._reza_get_request_by_token(token)
        if not grouped_request:
            return request.redirect("/returns/track")
        message = post.get("message", "").strip()
        if message:
            grouped_request.sudo().message_post(
                body=_("Guest customer message: %s", message),
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
        return request.redirect(
            f"/returns/request/{urllib.parse.quote(token)}?msg=sent"
        )

    @route("/returns/request/<string:token>/label", type="http", auth="public", website=True)
    def portal_guest_label_download(self, token, **kwargs):
        grouped_request = self._reza_get_request_by_token(token)
        if not grouped_request or not grouped_request.label_attachment_id:
            return request.redirect(f"/returns/request/{urllib.parse.quote(token)}")
        attachment = grouped_request.label_attachment_id
        content = base64.b64decode(attachment.datas or b"")
        headers = [
            ("Content-Type", attachment.mimetype or "application/pdf"),
            ("Content-Disposition", f'attachment; filename="{attachment.name or "return-label.pdf"}"'),
        ]
        return request.make_response(content, headers=headers)

    # ── Logged-in portal routes ──────────────────────────────────────────────

    @route("/my/rmas", type="http", auth="user", website=True)
    def portal_my_rmas(self, page=1, **kwargs):
        Request = request.env["reza.rma.request"].sudo()
        domain = self._reza_get_request_domain()
        request_count = Request.search_count(domain)
        pager = portal_pager(
            url="/my/rmas",
            total=request_count,
            page=page,
            step=10,
        )
        grouped_requests = Request.search(
            domain, limit=10, offset=pager["offset"], order="id desc"
        )
        rmas = grouped_requests.mapped("rma_ids")[:0]
        for grouped_request in grouped_requests:
            rmas |= grouped_request.rma_ids[:1]
        return request.render("reza_rma.portal_my_rmas", {
            "rmas": rmas,
            "pager": pager,
            "page_name": "rma_return",
            "submitted": kwargs.get("submitted") == "1",
        })

    @route("/my/rmas/<int:rma_id>", type="http", auth="user", website=True)
    def portal_rma_detail(self, rma_id, **kwargs):
        try:
            rma = self._reza_get_rma_or_raise(rma_id)
        except AccessError:
            return request.redirect("/my")
        return request.render("reza_rma.portal_rma_detail", {
            "rma": rma,
            "page_name": "rma_return",
            "submitted": kwargs.get("submitted") == "1",
        })

    @route("/my/rmas/new", type="http", auth="user", website=True)
    def portal_rma_new(self, **kwargs):
        partner = request.env.user.partner_id.commercial_partner_id
        return self._reza_render_create_form(partner)

    @route("/my/rmas/order_lines", type="jsonrpc", auth="user", website=True)
    def portal_rma_order_lines(self, order_id=None, **kwargs):
        if not order_id:
            return {"lines": []}

        partner = request.env.user.partner_id.commercial_partner_id
        order = request.env["sale.order"].sudo().browse(int(order_id))

        if not order.exists():
            return {"lines": [], "error": "Order not found."}
        if order.partner_id.commercial_partner_id.id != partner.id:
            return {"lines": [], "error": "Access denied."}
        if request.env.website and order.website_id.id != request.env.website.id:
            return {"lines": [], "error": "Access denied."}
        if not order.date_order:
            return {"lines": [], "error": "Invalid order."}

        deadline = order.company_id.reza_get_rma_return_deadline(order.date_order.date())
        if date.today() > deadline:
            return {"lines": [], "error": "Outside return window."}

        lines = []
        for line in order.order_line:
            if not line.product_id:
                continue
            if line.product_id.type == "service":
                continue
            product_tmpl = line.product_id.product_tmpl_id
            max_qty = self._reza_get_remaining_quantity(line)
            lines.append({
                "id": line.id,
                "product_id": line.product_id.id,
                "product_name": line.product_id.name,
                "qty": line.product_uom_qty,
                "qty_delivered": line.qty_delivered,
                "max_qty": max_qty,
                "uom": line.product_uom_id.name if line.product_uom_id else "",
                "already_returned": max_qty <= 0,
                "returnable": not product_tmpl.reza_non_returnable and max_qty > 0,
                "return_policy_note": product_tmpl.reza_return_policy_note or "",
            })

        return {"lines": lines}

    @route("/my/rmas/create", type="http", auth="user", website=True, methods=["POST"])
    def portal_rma_create(self, **post):
        partner = request.env.user.partner_id.commercial_partner_id
        error = {}

        # Step 1 — Order ownership
        try:
            order_id = int(post.get("sale_order_id", 0))
        except (ValueError, TypeError):
            order_id = 0
        order = request.env["sale.order"].sudo().browse(order_id)
        if not order.exists():
            error["sale_order_id"] = _("Invalid order.")
        elif order.partner_id.commercial_partner_id.id != partner.id:
            error["sale_order_id"] = _("This order does not belong to your account.")

        # Step 2 — Return window
        if not error.get("sale_order_id") and order.exists():
            if not order.date_order:
                error["sale_order_id"] = _("Order date is missing.")
            else:
                deadline = order.company_id.reza_get_rma_return_deadline(order.date_order.date())
                if date.today() > deadline:
                    error["sale_order_id"] = _(
                        "This order is outside the return window (deadline: %s).",
                        deadline,
                    )

        # Step 3 — Product lines
        raw_line_ids = request.httprequest.form.getlist("line_ids")
        if not raw_line_ids:
            error["lines"] = _("Please select at least one item to return.")

        valid_line_ids = []
        if not error.get("sale_order_id") and not error.get("lines") and order.exists():
            for lid_str in raw_line_ids:
                try:
                    lid = int(lid_str)
                except (ValueError, TypeError):
                    continue
                line = request.env["sale.order.line"].sudo().browse(lid)
                if (
                    line.exists()
                    and line.order_id.id == order.id
                    and line.product_id.type != "service"
                    and not line.product_id.product_tmpl_id.reza_non_returnable
                ):
                    valid_line_ids.append(lid)
            if not valid_line_ids:
                error["lines"] = _(
                    "No valid returnable items were selected."
                )

        # Step 4 — Reason
        try:
            reason_id = int(post.get("reza_reason_id", 0))
        except (ValueError, TypeError):
            reason_id = 0
        reason = request.env["reza.rma.reason"].sudo().browse(reason_id)
        if not reason.exists() or not reason.customer_selectable:
            error["reza_reason_id"] = _("Please select a valid return reason.")

        # Step 5 — Outcome
        operation_type = post.get("reza_operation_type")
        if operation_type not in ("credit_note", "store_credit", "exchange"):
            error["reza_operation_type"] = _("Please select a return outcome.")

        # Step 6 — Disclaimer
        if not post.get("reza_disclaimer_accepted"):
            error["disclaimer"] = _("You must accept the returns policy to proceed.")

        if error:
            return self._reza_render_create_form(
                partner, error=error, selected_order_id=order_id or None
            )

        return_method = post.get("reza_return_method", "auspost")
        if return_method not in ("auspost", "manual"):
            return_method = "auspost"

        selections = []
        for lid in valid_line_ids:
            line = request.env["sale.order.line"].sudo().browse(lid)
            qty_raw = post.get(f"qty_{lid}", "1")
            try:
                qty = float(qty_raw) if qty_raw else 1.0
            except (ValueError, TypeError):
                qty = 0.0
            remaining = self._reza_get_remaining_quantity(line)
            if qty <= 0 or qty > remaining:
                return self._reza_render_create_form(
                    partner,
                    error={"lines": _("Return quantity cannot exceed the remaining delivered quantity.")},
                    selected_order_id=order_id,
                )
            selections.append(
                {
                    "line": line,
                    "quantity": qty,
                    "reason": reason,
                    "notes": post.get("reza_customer_notes", "").strip(),
                }
            )

        grouped_request = self._reza_create_grouped_request(
            order,
            selections,
            operation_type,
            return_method=return_method,
            idempotency_seed=f"portal:{request.env.user.id}:{post.get('submission_token', '')}",
        )
        for rma in grouped_request.rma_ids:
            rma.reza_send_submitted_email()
        return request.redirect("/my/rmas?submitted=1")

    @route("/my/rmas/<int:rma_id>/message", type="http", auth="user", website=True, methods=["POST"])
    def portal_rma_message(self, rma_id, **post):
        try:
            rma = self._reza_get_rma_or_raise(rma_id)
        except AccessError:
            return request.redirect("/my")
        message = post.get("message", "").strip()
        if message:
            rma.sudo().message_post(
                body=message,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                author_id=request.env.user.partner_id.id,
            )
        return request.redirect(f"/my/rmas/{rma_id}")

    @route("/my/rmas/<int:rma_id>/label", type="http", auth="user", website=True)
    def portal_rma_label_download(self, rma_id, **kwargs):
        try:
            rma = self._reza_get_rma_or_raise(rma_id)
        except AccessError:
            return request.redirect("/my")
        attachment = rma.reza_return_label_attachment_id
        if rma.reza_request_line_id.request_id.label_attachment_id:
            attachment = rma.reza_request_line_id.request_id.label_attachment_id
        if not attachment:
            return request.redirect(f"/my/rmas/{rma_id}")
        content = base64.b64decode(attachment.datas or b"")
        headers = [
            ("Content-Type", attachment.mimetype or "application/pdf"),
            ("Content-Disposition", f'attachment; filename="{attachment.name or "return-label.pdf"}"'),
        ]
        return request.make_response(content, headers=headers)
