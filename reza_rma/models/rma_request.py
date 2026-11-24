import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


_logger = logging.getLogger(__name__)


REQUEST_STATES = [
    ("requested", "Requested"),
    ("label_pending", "Label Pending"),
    ("label_ready", "Label Ready"),
    ("in_transit", "In Transit"),
    ("received", "Received"),
    ("inspection_due", "Inspection Due"),
    ("resolution_pending", "Resolution Pending"),
    ("payment_due", "Payment Due"),
    ("resolved", "Resolved"),
    ("cancelled", "Cancelled"),
    ("migration_review", "Migration Review"),
]


class RezaRmaRequest(models.Model):
    _name = "reza.rma.request"
    _description = "Return Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, index=True, default=lambda self: _("New"))
    company_id = fields.Many2one(
        "res.company", required=True, index=True, default=lambda self: self.env.company
    )
    website_id = fields.Many2one("website", required=True, index=True, check_company=True)
    partner_id = fields.Many2one("res.partner", required=True, index=True)
    sale_order_id = fields.Many2one(
        "sale.order", required=True, index=True, check_company=True
    )
    line_ids = fields.One2many("reza.rma.request.line", "request_id", string="Items")
    rma_ids = fields.Many2many("rma", compute="_compute_related_records", string="RMAs")
    state = fields.Selection(
        REQUEST_STATES, required=True, default="requested", tracking=True, index=True
    )
    portal_access_token = fields.Char(required=True, copy=False, index=True)
    idempotency_key = fields.Char(required=True, copy=False, index=True)
    policy_version = fields.Char(required=True, default="1")
    policy_text_snapshot = fields.Text(required=True)
    policy_accepted_at = fields.Datetime(required=True, default=fields.Datetime.now)
    policy_accepted_ip_hash = fields.Char(copy=False)
    currency_id = fields.Many2one("res.currency", required=True)
    return_shipping_fee = fields.Monetary(required=True, default=0.0)
    return_shipping_actual_cost = fields.Monetary(default=0.0)
    expected_item_total = fields.Monetary(compute="_compute_amounts", store=True)
    expected_resolution_total = fields.Monetary(compute="_compute_amounts", store=True)
    label_state = fields.Selection(
        [
            ("pending", "Pending"),
            ("ready", "Ready"),
            ("failed", "Failed"),
            ("manual", "Manual"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="pending",
        tracking=True,
        index=True,
    )
    label_attachment_id = fields.Many2one("ir.attachment", copy=False)
    starshipit_order_ids = fields.Text(copy=False)
    carrier_tracking_ref = fields.Char(copy=False, index=True)
    carrier_tracking_url = fields.Char(copy=False)
    carrier_status = fields.Selection(
        [
            ("label_ready", "Label Ready"),
            ("in_transit", "In Transit"),
            ("delivered", "Delivered"),
            ("exception", "Exception"),
            ("lost", "Lost"),
        ],
        copy=False,
        tracking=True,
        index=True,
    )
    carrier_status_at = fields.Datetime(copy=False)
    label_attempt_count = fields.Integer(copy=False)
    label_last_error = fields.Text(copy=False)
    label_last_attempt_at = fields.Datetime(copy=False)
    receipt_picking_id = fields.Many2one("stock.picking", copy=False, check_company=True)
    migration_review_required = fields.Boolean(default=False, index=True)
    resolved_at = fields.Datetime(copy=False)

    _reza_rma_request_idempotency_unique = models.Constraint(
        'unique(idempotency_key)',
        "This return request has already been submitted.",
    )
    _reza_rma_request_token_unique = models.Constraint(
        'unique(portal_access_token)',
        "Return request access tokens must be unique.",
    )

    @api.depends("line_ids.item_total", "line_ids.expected_resolution_amount")
    def _compute_amounts(self):
        for request in self:
            request.expected_item_total = sum(request.line_ids.mapped("item_total"))
            request.expected_resolution_total = sum(
                request.line_ids.mapped("expected_resolution_amount")
            )

    @api.depends("line_ids.rma_id")
    def _compute_related_records(self):
        for request in self:
            request.rma_ids = request.line_ids.mapped("rma_id")

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("portal_access_token"):
                vals["portal_access_token"] = secrets.token_urlsafe(32)
            if not vals.get("idempotency_key"):
                vals["idempotency_key"] = secrets.token_hex(32)
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = sequence.next_by_code("reza.rma.request") or _("New")
        return super().create(vals_list)

    @api.constrains("company_id", "website_id", "sale_order_id")
    def _check_scope(self):
        for request in self:
            if request.website_id.company_id != request.company_id:
                raise ValidationError(_("The return website must belong to the request company."))
            if request.sale_order_id.company_id != request.company_id:
                raise ValidationError(_("The sale order must belong to the request company."))
            if request.sale_order_id.website_id and request.sale_order_id.website_id != request.website_id:
                raise ValidationError(_("The sale order must belong to the request website."))

    def _ensure_resolution_allowed(self, resolution=None):
        for request in self:
            invalid = request.line_ids.filtered(
                lambda line: line.inspection_outcome != "pass"
                or line.rma_id.state not in ("received", "refunded", "replaced", "finished")
            )
            if invalid:
                raise UserError(
                    _("Every selected item must be received and pass inspection before resolution.")
                )
            if resolution and request.line_ids.filtered(lambda line: line.resolution != resolution):
                raise UserError(_("This action does not match every selected item's resolution."))

    def action_retry_label(self):
        for request in self:
            if not request.company_id.reza_rma_enable_labels:
                raise UserError(
                    _("Automatic return labels are disabled until Starshipit passes staging verification.")
                )
            carrier = request.company_id.reza_rma_return_carrier_id
            if not carrier:
                raise UserError(
                    _("Configure a Return Starshipit Carrier before enabling automatic return labels.")
                )
            if carrier.website_id and carrier.website_id != request.website_id:
                raise UserError(
                    _("The configured Return Starshipit Carrier does not match this return website.")
                )
            carrier_model = self.env["delivery.carrier"]
            if not (
                hasattr(carrier_model, "starshipit_create_shipments")
                or hasattr(carrier_model, "starshipit_get_return_label")
            ):
                raise UserError(
                    _(
                        "The active Odoo 18 Starshipit runtime does not expose return-label creation. "
                        "Keep labels disabled until the existing integration is available."
                    )
                )
            if request.label_state == "ready":
                raise UserError(_("A return label already exists for this request."))
            request.write(
                {
                    "label_state": "pending",
                    "label_attempt_count": request.label_attempt_count + 1,
                    "label_last_attempt_at": fields.Datetime.now(),
                    "label_last_error": False,
                }
            )
            try:
                source_rma = request.rma_ids[:1]
                if not source_rma:
                    raise UserError(_("No item RMA is linked to this request."))
                attachment = source_rma._reza_generate_starshipit_return_label()
                request.write(
                    {
                        "label_state": "ready",
                        "state": "label_ready",
                        "label_attachment_id": attachment.id,
                        "carrier_tracking_ref": source_rma.reza_return_tracking_ref,
                        "starshipit_order_ids": getattr(
                            source_rma.reza_origin_delivery_picking_id, "orders", False
                        ),
                        "return_shipping_actual_cost": getattr(
                            source_rma.reza_origin_delivery_picking_id,
                            "starshipit_service_price",
                            0.0,
                        )
                        or 0.0,
                        "carrier_status": "label_ready",
                        "carrier_status_at": fields.Datetime.now(),
                    }
                )
            except Exception as error:
                error_str = str(error)
                _logger.exception("Return label generation failed for %s", request.name)
                is_config_error = "return products" in error_str.lower()
                request.write({
                    "label_state": "manual" if is_config_error else "failed",
                    "label_last_error": error_str,
                })
                if not is_config_error:
                    request.activity_schedule(
                        "mail.mail_activity_data_warning",
                        summary=_("Return label generation failed"),
                        note=_("Attempt %(attempt)s failed: %(error)s", attempt=request.label_attempt_count, error=error_str),
                    )
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_process_refund(self):
        if any(not request.company_id.reza_rma_enable_refunds for request in self):
            raise UserError(
                _("Scoped return refunds are disabled until accounting signs off staging totals.")
            )
        self._ensure_resolution_allowed("refund")
        for request in self:
            pending_rmas = request.line_ids.filtered(lambda line: not line.credit_note_id).mapped("rma_id")
            if pending_rmas:
                pending_rmas.with_context(_reza_refund_internal=True).action_refund()
            if request.line_ids.filtered(lambda line: not line.rma_id.refund_id):
                raise UserError(
                    _("OCA RMA could not create every scoped credit note. Verify the RMA state and operation configuration.")
                )
            for line in request.line_ids:
                if line.rma_id.refund_id:
                    line.write(
                        {
                            "credit_note_id": line.rma_id.refund_id.id,
                            "credit_note_line_id": line.rma_id.refund_line_id.id,
                            "payment_refund_state": "manual_required",
                        }
                    )
            request._add_return_shipping_charge()
            request._update_resolution_state()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_refund_original_payment(self):
        self._ensure_resolution_allowed("refund")
        for request in self:
            lines = request.line_ids.filtered(lambda line: line.resolution == "refund")
            unposted = lines.filtered(lambda line: line.credit_note_id.state != "posted")
            if unposted:
                raise UserError(_("Post every scoped credit note before refunding the original payment."))
            transactions = request.sale_order_id.transaction_ids.filtered(
                lambda transaction: transaction.state == "done"
            )
            if not transactions:
                lines.write({"payment_refund_state": "manual_required"})
                raise UserError(
                    _("No completed payment transaction was found. Process the refund manually.")
                )
            if len(transactions) != 1:
                lines.write({"payment_refund_state": "manual_required"})
                raise UserError(
                    _("Multiple completed payment transactions were found. Process the refund manually.")
                )
            transaction = transactions[0]
            support_refund = getattr(transaction.provider_id, "support_refund", False)
            if not support_refund or support_refund == "none":
                lines.write({"payment_refund_state": "manual_required"})
                request.activity_schedule(
                    "mail.mail_activity_data_warning",
                    summary=_("Manual original-payment refund required"),
                    note=_(
                        "Payment provider %(provider)s does not support automated refunds.",
                        provider=transaction.provider_id.display_name,
                    ),
                )
                raise UserError(
                    _("This payment provider does not support automated refunds. A staff activity was created.")
                )
            amount = sum(lines.mapped("credit_note_id").mapped("amount_total"))
            lines.write({"payment_refund_state": "pending"})
            try:
                transaction.action_refund(amount)
            except Exception as error:
                _logger.exception("Original payment refund failed for %s", request.name)
                lines.write({"payment_refund_state": "failed"})
                request.activity_schedule(
                    "mail.mail_activity_data_warning",
                    summary=_("Original payment refund requires review"),
                    note=str(error),
                )
                raise UserError(
                    _("The payment provider could not complete the refund. A staff activity was created.")
                ) from error
            lines.write({"payment_refund_state": "done"})
            request._update_resolution_state()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_confirm_store_credit_issued(self):
        self._ensure_resolution_allowed("store_credit")
        for request in self:
            program = request.company_id.reza_rma_store_credit_program_id
            if not program:
                raise UserError(
                    _("Configure an ecommerce payment-program loyalty program before issuing store credit.")
                )
            if program.program_type != "gift_card" or not program.ecommerce_ok:
                raise UserError(
                    _("The configured store-credit program must be an ecommerce gift-card program.")
                )
            for line in request.line_ids:
                if line.store_credit_id:
                    continue
                amount = line.expected_resolution_amount - line.shipping_fee_share
                bonus = self.env["reza.rma.store.credit.bonus"].search(
                    [
                        ("partner_id", "=", request.partner_id.commercial_partner_id.id),
                        ("company_id", "=", request.company_id.id),
                    ],
                    limit=1,
                )
                if not bonus:
                    percent = max(request.company_id.reza_rma_store_credit_bonus_percent, 0.0)
                    bonus_amount = request.currency_id.round(amount * percent / 100.0)
                    amount += bonus_amount
                    if bonus_amount > 0:
                        bonus = self.env["reza.rma.store.credit.bonus"].create(
                            {
                                "partner_id": request.partner_id.commercial_partner_id.id,
                                "company_id": request.company_id.id,
                                "request_id": request.id,
                                "amount": bonus_amount,
                                "currency_id": request.currency_id.id,
                            }
                        )
                if amount <= 0:
                    raise UserError(_("Store credit amount must be greater than zero."))
                card = self.env["loyalty.card"].create(
                    {
                        "program_id": program.id,
                        "partner_id": request.partner_id.id,
                        "company_id": request.company_id.id,
                        "points": amount,
                    }
                )
                line.write(
                    {
                        "store_credit_id": card.id,
                        "store_credit_reference": card.code,
                    }
                )
                if bonus and bonus.request_id == request:
                    line.rma_id.write(
                        {
                            "reza_store_credit_bonus_percent": request.company_id.reza_rma_store_credit_bonus_percent,
                            "reza_store_credit_bonus_amount": bonus.amount,
                        }
                    )
            request._update_resolution_state()
            codes = ", ".join(
                line.store_credit_reference for line in request.line_ids if line.store_credit_reference
            )
            request.message_post(
                body=_("Store credit issued. Gift card code: %s", codes),
                subtype_xmlid="mail.mt_note",
            )
            for line in request.line_ids:
                if line.rma_id:
                    line.rma_id.message_post(
                        body=_("Store credit issued. Gift card code: %s", codes),
                        subtype_xmlid="mail.mt_note",
                    )
                    line.rma_id.reza_send_done_email()
        return {"type": "ir.actions.client", "tag": "reload"}

    def _add_return_shipping_charge(self):
        self.ensure_one()
        if not self.return_shipping_fee:
            return
        product = self.company_id.reza_rma_return_shipping_product_id
        if not product:
            raise UserError(
                _("Configure a Return Shipping Charge Product before processing refunds.")
            )
        credit_notes = self.line_ids.mapped("credit_note_id")
        if len(credit_notes) != 1:
            raise UserError(
                _("The return shipping charge requires one credit note for this request; review multi-invoice returns manually.")
            )
        credit_note = credit_notes[0]
        if credit_note.state != "draft":
            raise UserError(_("The return shipping charge can only be added to a draft credit note."))
        if credit_note.invoice_line_ids.filtered(lambda line: line.reza_rma_request_id == self):
            return
        account = product.property_account_income_id or product.categ_id.property_account_income_categ_id
        if not account:
            raise UserError(_("The Return Shipping Charge Product needs an income account."))
        self.env["account.move.line"].create(
            {
                "move_id": credit_note.id,
                "name": _("Return shipping charge"),
                "product_id": product.id,
                "quantity": 1.0,
                "price_unit": -self.return_shipping_fee,
                "account_id": account.id,
                "tax_ids": [(6, 0, product.taxes_id.filtered(lambda tax: tax.company_id == self.company_id).ids)],
                "reza_rma_request_id": self.id,
            }
        )

    def action_process_exchange(self):
        if any(not request.company_id.reza_rma_enable_exchanges for request in self):
            raise UserError(
                _("Exchanges are disabled until stock and payment gates pass staging verification.")
            )
        self._ensure_resolution_allowed("exchange")
        for request in self:
            for line in request.line_ids:
                if not line.exchange_product_id:
                    raise UserError(_("Select an exact exchange product for every exchange item."))
                if line.exchange_order_id:
                    continue
                if line.exchange_difference < 0 and not line.store_credit_reference:
                    raise UserError(
                        _("Enter the approved store-credit reference for a cheaper exchange before creating the exchange order.")
                    )
                order = self.env["sale.order"].create(
                    {
                        "partner_id": request.partner_id.id,
                        "company_id": request.company_id.id,
                        "website_id": request.website_id.id,
                        "origin": request.name,
                        "note": _("Exchange order for return %s", request.name),
                        "reza_rma_request_id": request.id,
                    }
                )
                self.env["sale.order.line"].create(
                    {
                        "order_id": order.id,
                        "product_id": line.exchange_product_id.id,
                        "product_uom_qty": line.exchange_quantity or line.quantity,
                        "price_unit": line.exchange_product_id.lst_price,
                    }
                )
                order.action_confirm()
                line.write(
                    {
                        "exchange_order_id": order.id,
                        "exchange_delivery_id": order.picking_ids[:1].id,
                        "reservation_expires_at": fields.Datetime.now()
                        + timedelta(hours=request.company_id.reza_rma_exchange_hold_hours),
                    }
                )
            request._update_resolution_state()
        return {"type": "ir.actions.client", "tag": "reload"}

    def _update_resolution_state(self):
        for request in self:
            resolved = all(
                (
                    line.resolution == "refund"
                    and line.credit_note_id.state == "posted"
                    and line.payment_refund_state == "done"
                )
                or (
                    line.resolution == "exchange"
                    and line.exchange_delivery_id.state == "done"
                )
                or (line.resolution == "store_credit" and line.store_credit_reference)
                for line in request.line_ids
            )
            if resolved:
                request.write({"state": "resolved", "resolved_at": fields.Datetime.now()})
            elif request.line_ids.filtered(
                lambda line: line.exchange_difference > 0
                and (
                    not line.payment_transaction_id
                    or line.payment_transaction_id.state != "done"
                )
            ):
                request.state = "payment_due"
            else:
                request.state = "resolution_pending"

    @api.model
    def _cron_retry_failed_labels(self):
        requests = self.search(
            [("label_state", "=", "failed"), ("label_attempt_count", "<", 3)],
            limit=50,
        )
        for request in requests:
            request.action_retry_label()

    @api.model
    def _cron_expire_exchange_holds(self):
        lines = self.env["reza.rma.request.line"].search(
            [
                ("reservation_expires_at", "<", fields.Datetime.now()),
                ("exchange_order_id", "!=", False),
                ("exchange_order_id.state", "in", ["draft", "sent", "sale"]),
                ("exchange_delivery_id.state", "!=", "done"),
            ],
            limit=100,
        )
        for line in lines:
            transaction = line.payment_transaction_id
            if transaction and transaction.state == "done":
                continue
            line.exchange_order_id.action_cancel()
            line.request_id.message_post(
                body=_("Exchange reservation expired for %s.", line.product_id.display_name),
                subtype_xmlid="mail.mt_note",
            )
            line.reservation_expires_at = False


class RezaRmaRequestLine(models.Model):
    _name = "reza.rma.request.line"
    _description = "Return Request Item"
    _inherit = ["mail.thread"]
    _order = "request_id, id"
    _check_company_auto = True

    request_id = fields.Many2one(
        "reza.rma.request", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="request_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="request_id.currency_id", store=True)
    rma_id = fields.Many2one("rma", required=True, copy=False, index=True, ondelete="restrict")
    sale_order_line_id = fields.Many2one(
        "sale.order.line", required=True, index=True, ondelete="restrict"
    )
    source_move_id = fields.Many2one("stock.move", copy=False, index=True)
    product_id = fields.Many2one("product.product", required=True, index=True)
    uom_id = fields.Many2one("uom.uom", required=True)
    quantity = fields.Float(required=True, digits="Product Unit")
    reason_id = fields.Many2one("reza.rma.reason", required=True)
    resolution = fields.Selection(
        [("refund", "Refund"), ("store_credit", "Store Credit"), ("exchange", "Exchange")],
        required=True,
        index=True,
    )
    item_untaxed = fields.Monetary(default=0.0)
    item_tax = fields.Monetary(default=0.0)
    item_total = fields.Monetary(default=0.0)
    shipping_fee_share = fields.Monetary(default=0.0)
    expected_resolution_amount = fields.Monetary(default=0.0)
    inspection_outcome = fields.Selection(
        [("pass", "Pass"), ("fail", "Fail")], tracking=True, index=True
    )
    disposition = fields.Selection(
        [
            ("restock", "Restock"),
            ("refurbish", "Refurbish"),
            ("quarantine", "Quarantine"),
            ("discard", "Discard"),
            ("return_customer", "Return to Customer"),
        ],
        tracking=True,
    )
    inspection_notes = fields.Text()
    credit_note_id = fields.Many2one("account.move", copy=False)
    credit_note_line_id = fields.Many2one("account.move.line", copy=False)
    refund_payment_id = fields.Many2one("account.payment", copy=False)
    payment_refund_state = fields.Selection(
        [
            ("not_required", "Not Required"),
            ("manual_required", "Manual Refund Required"),
            ("pending", "Pending"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="not_required",
        copy=False,
        tracking=True,
    )
    store_credit_reference = fields.Char(copy=False)
    store_credit_id = fields.Many2one("loyalty.card", copy=False)
    exchange_product_id = fields.Many2one("product.product")
    exchange_quantity = fields.Float(digits="Product Unit")
    exchange_value = fields.Monetary(compute="_compute_exchange_amounts", store=True)
    exchange_difference = fields.Monetary(compute="_compute_exchange_amounts", store=True)
    exchange_order_id = fields.Many2one("sale.order", copy=False)
    exchange_delivery_id = fields.Many2one("stock.picking", copy=False)
    payment_transaction_id = fields.Many2one("payment.transaction", copy=False)
    reservation_expires_at = fields.Datetime(copy=False)
    resolution_idempotency_key = fields.Char(copy=False, index=True)

    _reza_rma_request_line_rma_unique = models.Constraint(
        'unique(rma_id)',
        "An RMA can belong to only one return request.",
    )
    _reza_rma_resolution_key_unique = models.Constraint(
        'unique(resolution_idempotency_key)',
        "This return resolution has already been processed.",
    )
    _reza_rma_request_line_qty_positive = models.Constraint(
        'check(quantity > 0)',
        "Return quantity must be greater than zero.",
    )

    @api.depends("exchange_product_id", "exchange_quantity", "quantity", "item_total")
    def _compute_exchange_amounts(self):
        for line in self:
            quantity = line.exchange_quantity or line.quantity
            line.exchange_value = line.exchange_product_id.lst_price * quantity
            line.exchange_difference = line.exchange_value - line.item_total

    def write(self, vals):
        result = super().write(vals)
        if {
            "payment_refund_state",
            "payment_transaction_id",
            "exchange_delivery_id",
            "store_credit_reference",
        }.intersection(vals):
            self.mapped("request_id")._update_resolution_state()
        return result

    @api.constrains("quantity", "sale_order_line_id", "rma_id")
    def _check_quantity(self):
        for line in self:
            max_qty = line.sale_order_line_id.qty_delivered
            other_qty = sum(
                self.search(
                    [
                        ("id", "!=", line.id),
                        ("sale_order_line_id", "=", line.sale_order_line_id.id),
                        ("request_id.state", "not in", ["cancelled"]),
                    ]
                ).mapped("quantity")
            )
            if line.uom_id.compare(line.quantity + other_qty, max_qty) > 0:
                raise ValidationError(
                    _("Total active return quantity cannot exceed the delivered quantity.")
                )
            if line.rma_id.sale_line_id and line.rma_id.sale_line_id != line.sale_order_line_id:
                raise ValidationError(_("The request line and RMA must use the same sale order line."))


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    reza_rma_request_id = fields.Many2one("reza.rma.request", copy=False, index=True)


class RezaRmaLookupAttempt(models.Model):
    _name = "reza.rma.lookup.attempt"
    _description = "Return Lookup Attempt"
    _order = "create_date desc"

    ip_hash = fields.Char(required=True, index=True)
    lookup_hash = fields.Char(required=True, index=True)
    website_id = fields.Many2one("website", required=True, index=True, ondelete="cascade")
    successful = fields.Boolean(default=False)

    @api.model
    def _cron_purge_expired(self):
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=7)
        self.search([("create_date", "<", cutoff)]).unlink()


class RezaRmaStoreCreditBonus(models.Model):
    _name = "reza.rma.store.credit.bonus"
    _description = "First Return Store Credit Bonus"
    _order = "create_date desc"
    _check_company_auto = True

    partner_id = fields.Many2one("res.partner", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one("res.company", required=True, index=True, ondelete="restrict")
    request_id = fields.Many2one("reza.rma.request", required=True, ondelete="restrict")
    currency_id = fields.Many2one("res.currency", required=True)
    amount = fields.Monetary(required=True)

    _reza_rma_store_credit_bonus_unique = models.Constraint(
        'unique(partner_id, company_id)',
        "The first-return store-credit bonus can only be issued once per customer and company.",
    )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    reza_rma_request_id = fields.Many2one("reza.rma.request", copy=False, index=True)


class RmaOperation(models.Model):
    _inherit = "rma.operation"

    @api.constrains(
        "action_create_refund",
        "action_create_delivery",
        "auto_confirm_reception",
    )
    def _check_reza_manual_after_receipt(self):
        for operation in self:
            if operation.auto_confirm_reception:
                raise ValidationError(
                    _("RMA reception validation must remain manual so warehouse receipt is explicit.")
                )
            if operation.action_create_refund in (
                "automatic_on_confirm",
                "automatic_after_receipt",
                "update_quantity",
            ):
                raise ValidationError(
                    _("Automatic RMA refunds are disabled so inspection cannot be bypassed.")
                )
            if operation.action_create_delivery in (
                "automatic_on_confirm",
                "automatic_after_receipt",
            ):
                raise ValidationError(
                    _("Automatic RMA replacement delivery is disabled so inspection cannot be bypassed.")
                )
