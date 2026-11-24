import ast
import logging

from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


class Rma(models.Model):
    _inherit = "rma"

    # Reason
    reza_reason_id = fields.Many2one(
        comodel_name="reza.rma.reason",
        string="Return Reason",
    )

    # Customer preferred outcome
    reza_operation_type = fields.Selection(
        [
            ("credit_note", "Refund to Original Payment"),
            ("store_credit", "Store Credit"),
            ("exchange", "Exchange / Replacement"),
        ],
        string="Requested Outcome",
    )

    # Return shipping method
    reza_return_method = fields.Selection(
        [
            ("auspost", "Australia Post Returns Portal"),
            ("manual", "Manual — Warehouse Address Provided"),
        ],
        string="Return Method",
        default="auspost",
    )

    # Customer condition declarations
    reza_tags_attached = fields.Boolean(string="Tags Attached", default=False)
    reza_original_packaging = fields.Boolean(string="Original Packaging", default=False)
    reza_no_signs_of_wear = fields.Boolean(string="No Signs of Wear", default=False)
    reza_customer_notes = fields.Text(string="Customer Notes")
    reza_damage_on_arrival = fields.Boolean(
        string="Damage / Fault Claim",
        default=False,
        help="Routes to manual review — does not auto-reject.",
    )

    # Staff inspection
    reza_inspection_outcome = fields.Selection(
        [
            ("acceptable", "Acceptable — Condition Met"),
            ("damaged_used", "Damaged / Used — Return to Customer"),
            ("missing_packaging", "Missing Original Packaging"),
        ],
        string="Inspection Outcome",
    )
    reza_inspection_notes = fields.Text(string="Inspection Notes")

    # SLA
    reza_warehouse_received_date = fields.Datetime(string="Warehouse Received Date")
    reza_sla_due_date = fields.Datetime(
        string="SLA Due Date",
        compute="_compute_reza_sla_due",
        store=True,
    )
    reza_sla_alerted = fields.Boolean(string="SLA Alerted", default=False)

    # Portal visibility
    reza_portal_visible = fields.Boolean(string="Visible on Portal", default=True)

    # Portal display fields (computed, not stored)
    reza_portal_state_label = fields.Char(
        compute="_compute_reza_portal_display",
        string="Portal Status Label",
    )
    reza_portal_badge_class = fields.Char(
        compute="_compute_reza_portal_display",
        string="Portal Badge Class",
    )
    reza_store_credit_bonus_percent = fields.Float(
        string="Store Credit Bonus %",
        readonly=True,
        copy=False,
    )
    reza_store_credit_bonus_amount = fields.Float(
        string="Store Credit Bonus Amount",
        readonly=True,
        copy=False,
    )
    reza_store_credit_issued = fields.Boolean(
        compute="_compute_reza_store_credit_issued",
        string="Store Credit Issued",
    )

    def _compute_reza_store_credit_issued(self):
        for rma in self:
            rma.reza_store_credit_issued = bool(rma.reza_request_line_id.store_credit_id)
    reza_return_label_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Return Label Attachment",
        copy=False,
    )
    reza_return_tracking_ref = fields.Char(
        string="Return Tracking Reference",
        copy=False,
    )
    reza_return_label_generated_at = fields.Datetime(
        string="Return Label Generated At",
        copy=False,
    )
    reza_return_carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        string="Return Carrier",
        copy=False,
    )
    reza_origin_delivery_picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Original Delivery Picking",
        copy=False,
    )
    reza_can_generate_return_label = fields.Boolean(
        compute="_compute_reza_can_generate_return_label",
        string="Can Generate Return Label",
    )
    reza_return_shipping_fee = fields.Float(
        string="Return Shipping Fee",
        digits=(16, 2),
        default=0.0,
        copy=False,
        help="Return shipping cost to be deducted from the customer's refund.",
    )
    reza_exchange_preference = fields.Text(
        string="Exchange Preference",
        help="Customer's description of the replacement item they want.",
    )
    reza_disclaimer_accepted = fields.Boolean(
        string="Returns Policy Accepted",
        default=False,
    )
    reza_request_line_id = fields.Many2one(
        "reza.rma.request.line",
        string="Return Request Item",
        copy=False,
        index=True,
        ondelete="restrict",
    )
    reza_migration_review_required = fields.Boolean(
        string="Migration Review Required",
        default=False,
        index=True,
        copy=False,
    )
    reza_staff_summary = fields.Char(
        string="Staff Flag",
        compute="_compute_reza_staff_summary",
        store=True,
        help="Short staff-facing summary of requested outcome, reason, and customer issue.",
    )

    @api.depends("reza_warehouse_received_date")
    def _compute_reza_sla_due(self):
        for rec in self:
            if rec.reza_warehouse_received_date:
                rec.reza_sla_due_date = rec.reza_warehouse_received_date + timedelta(days=2)
            else:
                rec.reza_sla_due_date = False

    @api.depends("state")
    def _compute_reza_portal_display(self):
        label_map = {
            "draft": ("Submitted", "bg-info"),
            "confirmed": ("Under Review", "bg-warning text-dark"),
            "received": ("Received by Warehouse", "bg-info"),
            "waiting_return": ("Awaiting Return", "bg-warning text-dark"),
            "waiting_replacement": ("Processing", "bg-warning text-dark"),
            "refunded": ("Processed — Refund Issued", "bg-success"),
            "returned": ("Processed — Returned", "bg-success"),
            "replaced": ("Processed — Exchange Sent", "bg-success"),
            "finished": ("Closed", "bg-secondary"),
            "locked": ("Closed", "bg-secondary"),
            "cancelled": ("Cancelled", "bg-secondary"),
        }
        for rec in self:
            label, badge = label_map.get(rec.state, ("In Progress", "bg-info"))
            rec.reza_portal_state_label = label
            rec.reza_portal_badge_class = badge

    @api.depends("reza_operation_type", "reza_reason_id", "reza_customer_notes", "reza_damage_on_arrival")
    def _compute_reza_staff_summary(self):
        outcome_map = {
            "credit_note": _("Refund"),
            "store_credit": _("Store Credit"),
            "exchange": _("Replacement"),
        }
        for rec in self:
            parts = []
            if rec.reza_operation_type:
                parts.append(outcome_map.get(rec.reza_operation_type, rec.reza_operation_type))
            if rec.reza_reason_id:
                parts.append(rec.reza_reason_id.display_name)
            if rec.reza_damage_on_arrival:
                parts.append(_("Damage/Fault"))
            note = (rec.reza_customer_notes or "").strip()
            if note:
                parts.append(note[:60] + ("..." if len(note) > 60 else ""))
            rec.reza_staff_summary = " | ".join(parts)

    @api.depends("reza_return_method", "picking_id", "order_id")
    def _compute_reza_can_generate_return_label(self):
        for rec in self:
            rec.reza_can_generate_return_label = bool(
                rec.reza_return_method == "auspost"
                and rec._reza_get_starshipit_label_picking(create_missing=False)
            )

    def unlink(self):
        non_deletable = self.filtered(lambda r: r.state not in ("draft", "cancelled"))
        if non_deletable:
            raise UserError(
                _("Only draft or cancelled RMAs can be deleted.")
            )
        # OCA's unlink only adds a draft-only state gate then calls super; bypass
        # it here (after our own broader check) so cancelled records can be deleted.
        return models.Model.unlink(self)

    def write(self, vals):
        result = super().write(vals)
        if vals.get("state") == "received":
            for rma in self.filtered("reza_request_line_id"):
                if not rma.reza_warehouse_received_date:
                    rma.reza_warehouse_received_date = fields.Datetime.now()
                request = rma.reza_request_line_id.request_id
                all_received = all(
                    item.state in ("received", "refunded", "replaced", "finished")
                    for item in request.rma_ids
                )
                request.write(
                    {
                        "state": "inspection_due" if all_received else "received",
                        "receipt_picking_id": rma.reception_move_id.picking_id.id,
                    }
                )
        return result

    def _check_return_window(self):
        self.ensure_one()
        sale_order = self.order_id
        if not sale_order:
            return
        order_date = sale_order.date_order
        if not order_date:
            return
        deadline = sale_order.company_id.reza_get_rma_return_deadline(order_date.date())
        if fields.Date.today() > deadline:
            raise ValidationError(
                _(
                    "This order is outside the return window. "
                    "The return deadline was %s.",
                    deadline,
                )
            )

    def _reza_get_starshipit_label_picking(self, create_missing=True):
        self.ensure_one()
        request = self.reza_request_line_id.request_id
        if request.receipt_picking_id:
            return request.receipt_picking_id
        if self.reception_move_id.picking_id:
            return self.reception_move_id.picking_id
        if not create_missing:
            return self.env["stock.picking"]
        if self.state == "draft":
            self.action_confirm()
        elif (
            self.operation_id.action_create_receipt
            and not self.reception_move_id
        ):
            self.action_create_receipt()
        return self.reception_move_id.picking_id

    def _reza_get_starshipit_source_picking(self):
        """Original delivery used by Odoo 18's Starshipit return-label helper."""
        self.ensure_one()
        picking = self.picking_id or self.move_id.picking_id
        if not picking:
            raise UserError(
                _("No original delivery picking was found for this return.")
            )
        return picking

    def _reza_get_return_carrier(self):
        self.ensure_one()
        carrier = self.company_id.reza_rma_return_carrier_id
        if not carrier:
            raise UserError(
                _(
                    "No Return Starshipit Carrier is configured for %(company)s.",
                    company=self.company_id.display_name,
                )
            )
        if not carrier.active:
            raise UserError(_("The configured return carrier must be active."))
        if not (
            hasattr(carrier, "starshipit_get_return_label")
            or hasattr(carrier, "starshipit_create_shipments")
        ):
            raise UserError(
                _("The configured return carrier does not expose the loaded Starshipit return-label API.")
            )
        request_line = self.reza_request_line_id
        website = request_line.request_id.website_id if request_line else self.order_id.website_id
        if carrier.website_id and carrier.website_id != website:
            raise UserError(
                _("The configured return carrier does not belong to this return's website.")
            )
        return carrier

    def _reza_starshipit_address_payload(self, partner):
        self.ensure_one()
        missing = []
        for field_name in ("name", "street", "city", "zip", "country_id"):
            if not partner[field_name]:
                missing.append(field_name)
        if missing:
            raise UserError(
                _(
                    "Please fill in %(fields)s on the %(partner)s partner before creating a return label.",
                    fields=", ".join(missing),
                    partner=partner.display_name,
                )
            )
        return {
            "name": partner.name,
            "email": partner.email or "",
            "phone": partner.phone or "",  # res.partner.mobile is gone in Odoo 20
            "street": partner.street or "",
            "suburb": partner.street2 or "",
            "city": partner.city or "",
            "state": partner.state_id.code or partner.state_id.name or "",
            "post_code": partner.zip or "",
            "country": partner.country_id.name or "",
            "country_code": partner.country_id.code or "",
        }

    def _reza_starshipit_return_package_payload(self, picking):
        self.ensure_one()
        weight = picking.shipping_weight or picking.weight or picking.weight_bulk
        if not weight:
            for move in picking.move_ids:
                quantity = move.product_uom_qty or move.quantity or self.product_uom_qty or 1.0
                weight += (move.product_id.weight or 0.0) * quantity
        if not weight:
            weight = 0.5  # safe staging default — update product weights for production
        return {
            "weight": round(weight, 2),
            "height": 0.05,
            "width": 0.20,
            "length": 0.30,
        }

    def _reza_starshipit_return_items_payload(self, picking):
        self.ensure_one()
        items = []
        for move in picking.move_ids:
            if not move.product_id:
                continue
            qty = move.product_uom_qty or move.quantity or 1.0
            sale_line = move.sale_line_id
            items.append({
                "description": move.product_id.name or "Return Item",
                "sku": move.product_id.default_code or "",
                "quantity": int(qty),
                "value": round(float(sale_line.price_unit if sale_line else 0.0), 2),
                "weight": round(float(move.product_id.weight or 0.0), 3),
            })
        if not items:
            qty = self.product_uom_qty or 1.0
            sale_line = self.move_id.sale_line_id if self.move_id else None
            items = [{
                "description": self.product_id.name or "Return Item",
                "sku": self.product_id.default_code or "",
                "quantity": int(qty),
                "value": round(float(sale_line.price_unit if sale_line else 0.0), 2),
                "weight": round(float(self.product_id.weight or 0.0), 3),
            }]
        return items

    def _reza_generate_starshipit_return_label_direct(self, carrier, receipt_picking):
        self.ensure_one()
        api_key = getattr(carrier, "starshipit_api_key", False)
        subscription_key = getattr(carrier, "starshipit_subscription_key", False)
        if not api_key or not subscription_key:
            return False

        request_record = self.reza_request_line_id.request_id
        warehouse = receipt_picking.picking_type_id.warehouse_id or self.order_id.warehouse_id
        # Starshipit requires sender=your-account (company/warehouse) and destination=customer
        # even for return labels.  return_order:True tells Starshipit to print the label
        # in the reverse direction (customer→company) while keeping the account as sender.
        sender_partner = warehouse.partner_id or self.company_id.partner_id
        destination_partner = self.partner_shipping_id or self.partner_id
        sender = self._reza_starshipit_address_payload(sender_partner)
        destination = self._reza_starshipit_address_payload(destination_partner)
        package = self._reza_starshipit_return_package_payload(receipt_picking)
        items = self._reza_starshipit_return_items_payload(receipt_picking)
        order_number = "%s#%s-%s" % (
            receipt_picking.name,
            request_record.id or self.id,
            request_record.label_attempt_count or 1,
        )
        payload = {
            "orders": [
                {
                    "order_number": order_number,
                    "reference": self.name,
                    "shipping_method": carrier.starshipit_service_name or carrier.name,
                    "sender": sender,
                    "destination": destination,
                    "return_order": True,
                    "package": package,
                    "items": items,
                }
            ]
        }
        headers = {
            "Content-Type": "application/json",
            "StarShipIT-Api-Key": api_key,
            "Ocp-Apim-Subscription-Key": subscription_key,
        }
        try:
            response = requests.post(
                "https://api.starshipit.com/api/orders/import",
                json=payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            import_result = response.json()
            if not import_result.get("success", False):
                errors = import_result.get("errors") or import_result.get("messages") or import_result
                raise UserError(_("Starshipit order import failed: %s", errors))
            order_ids = [order["order_id"] for order in import_result.get("orders", []) if order.get("order_id")]
            if not order_ids:
                raise UserError(_("Starshipit did not return a return order id."))

            response = requests.post(
                "https://api.starshipit.com/api/orders/shipments",
                json={"order_ids": order_ids},
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            shipment_result = response.json()
            if not shipment_result.get("success", False):
                errors = shipment_result.get("errors") or shipment_result.get("messages") or shipment_result
                if "return products" in str(errors).lower():
                    raise UserError(_(
                        "Starshipit return products are not configured — label_state will be set "
                        "to manual. To fix: Starshipit → Settings → Carriers → your carrier → "
                        "enable Return Services and add a return product. "
                        "Starshipit error: %s"
                    ) % (errors,))
                raise UserError(_("Starshipit label creation failed: %s", errors))
        except requests.RequestException as error:
            raise UserError(_("Starshipit API request failed: %s", error)) from error

        labels = shipment_result.get("labels") or []
        if not labels or not labels[0].get("label_base64_string"):
            import json as _json
            raise UserError(_(
                "Starshipit did not return a label PDF. Full shipments response: %s",
                _json.dumps(shipment_result, default=str)[:2000],
            ))
        picking_vals = {"carrier_id": carrier.id}
        if "orders" in self.env["stock.picking"]._fields:
            picking_vals["orders"] = str(order_ids)
        receipt_picking.write(picking_vals)
        return {
            "label": labels[0]["label_base64_string"],
            "orders": str(order_ids),
            "tracking": ",".join(map(str, order_ids)),
            "picking": receipt_picking,
        }

    def _reza_prepare_store_credit_bonus(self):
        self.ensure_one()
        if self.reza_operation_type != "store_credit":
            return {"percent": 0.0, "amount": 0.0}
        sibling_bonus = self.env["rma"].search_count([
            ("id", "!=", self.id),
            ("partner_id", "child_of", self.partner_id.commercial_partner_id.id),
            ("state", "not in", ["cancelled"]),
            ("reza_operation_type", "=", "store_credit"),
            ("reza_store_credit_bonus_amount", ">", 0),
        ])
        if sibling_bonus:
            return {"percent": 0.0, "amount": 0.0}
        percent = max(self.company_id.reza_rma_store_credit_bonus_percent, 0.0)
        invoices = self.order_id.invoice_ids.filtered(
            lambda move: move.move_type == "out_invoice" and move.state == "posted"
        )
        base_amount = invoices[:1].amount_total if invoices else 0.0
        bonus_amount = 0.0
        if base_amount and percent:
            bonus_amount = self.company_id.currency_id.round(base_amount * (percent / 100.0))
        return {"percent": percent, "amount": bonus_amount}

    def _reza_generate_starshipit_return_label(self):
        self.ensure_one()
        receipt_picking = self._reza_get_starshipit_label_picking()
        if not receipt_picking:
            raise UserError(
                _(
                    "No customer-to-warehouse return receipt picking was found for this return."
                )
            )
        carrier = self._reza_get_return_carrier()
        label_b64 = False
        tracking_ref = False
        orders_value = False
        starshipit_picking = receipt_picking
        direct_response = self._reza_generate_starshipit_return_label_direct(
            carrier, receipt_picking
        )
        if direct_response:
            label_b64 = direct_response["label"]
            orders_value = direct_response["orders"]
            tracking_ref = direct_response["tracking"]
            starshipit_picking = direct_response["picking"]
        elif hasattr(carrier, "starshipit_create_shipments"):
            picking = receipt_picking
            picking.carrier_id = carrier
            response = carrier.starshipit_create_shipments(picking, return_order=True)
            label_b64 = response[0]
            orders_value = getattr(picking, "orders", False) or response[1]
        elif hasattr(carrier, "starshipit_get_return_label"):
            picking = self._reza_get_starshipit_source_picking()
            picking.carrier_id = carrier
            starshipit_picking = picking
            outbound_tracking = picking.carrier_tracking_ref
            before_attachments = picking.message_ids.attachment_ids
            carrier.starshipit_get_return_label(
                picking,
                outbound_tracking or "",
                picking.date_done or picking.scheduled_date,
            )
            new_attachments = picking.message_ids.attachment_ids - before_attachments
            label_attachment = new_attachments.filtered(
                lambda attachment: attachment.mimetype == "application/pdf"
                or "return label" in (attachment.name or "").lower()
            )[:1]
            picking.carrier_tracking_ref = outbound_tracking
            if not label_attachment:
                raise UserError(
                    _("Starshipit did not create a return-label PDF attachment.")
                )
            label_b64 = label_attachment.datas
            orders_value = getattr(picking, "orders", False)
        else:
            raise UserError(
                _("The active Odoo 18 Starshipit runtime has no return-label method.")
            )
        if orders_value:
            try:
                tracking_ref = ",".join(map(str, ast.literal_eval(orders_value)))
            except (SyntaxError, ValueError):
                tracking_ref = orders_value

        attachment_vals = {
            "name": f"Return Label {self.name}.pdf",
            "datas": label_b64,
            "mimetype": "application/pdf",
            "res_model": "rma",
            "res_id": self.id,
        }
        if self.reza_return_label_attachment_id:
            self.reza_return_label_attachment_id.write(attachment_vals)
            attachment = self.reza_return_label_attachment_id
        else:
            attachment = self.env["ir.attachment"].create(attachment_vals)

        self.write({
            "reza_return_label_attachment_id": attachment.id,
            "reza_return_tracking_ref": tracking_ref,
            "reza_return_label_generated_at": fields.Datetime.now(),
            "reza_return_carrier_id": carrier.id,
            "reza_origin_delivery_picking_id": starshipit_picking.id,
        })
        self.message_post(
            body=_("Return label generated via Starshipit."),
            attachment_ids=[attachment.id],
            subtype_xmlid="mail.mt_note",
        )
        return attachment

    # ── Email trigger methods ────────────────────────────────────────────────

    def reza_send_submitted_email(self):
        template = self.env.ref("reza_rma.mail_template_rma_submitted", raise_if_not_found=False)
        if not template:
            return
        email_values = {}
        if self.reza_return_label_attachment_id:
            email_values["attachment_ids"] = [self.reza_return_label_attachment_id.id]
        template.send_mail(self.id, force_send=True, email_values=email_values or None)

    def reza_send_approved_email(self):
        if self.reza_return_method == "auspost":
            ref = "reza_rma.mail_template_rma_approved_auspost"
        else:
            ref = "reza_rma.mail_template_rma_approved_manual"
        template = self.env.ref(ref, raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)

    def reza_send_rejection_email(self):
        template = self.env.ref("reza_rma.mail_template_rma_rejected", raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)

    def reza_send_damaged_email(self):
        template = self.env.ref("reza_rma.mail_template_rma_damaged_return", raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)

    def reza_send_done_email(self):
        template = self.env.ref("reza_rma.mail_template_rma_done", raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)

    # ── Backend action methods ───────────────────────────────────────────────

    def reza_action_set_inspection(self):
        self.ensure_one()
        if self.state not in ("received", "refunded", "replaced", "finished"):
            raise UserError(_("The returned item must be received before inspection."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Record Inspection"),
            "res_model": "reza.rma.inspect.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_rma_id": self.id},
        }

    def action_refund(self):
        # When called internally from action_process_refund(), bypass the redirect
        # to avoid infinite recursion.
        if self.env.context.get("_reza_refund_internal"):
            return super().action_refund()
        # For RMAs linked to a grouped reza.rma.request, route through our safe flow so
        # the return shipping charge is deducted and the resolution guard fires.
        linked = self.filtered(lambda r: r.reza_request_line_id)
        unlinked = self - linked
        result = None
        if linked:
            grouped_requests = linked.mapped("reza_request_line_id.request_id")
            result = grouped_requests.action_process_refund()
        if unlinked:
            result = super(Rma, unlinked).action_refund()
        return result or {"type": "ir.actions.client", "tag": "reload"}

    def reza_action_process_credit_note(self):
        self.ensure_one()
        if not self.reza_request_line_id:
            raise UserError(
                _("This legacy RMA must be linked to a Return Request before a safe scoped credit note can be created.")
            )
        return self.reza_request_line_id.request_id.action_process_refund()

    def reza_action_process_store_credit(self):
        self.ensure_one()
        if not self.reza_request_line_id:
            raise UserError(
                _("This legacy RMA must be linked to a Return Request before store credit can be issued.")
            )
        return self.reza_request_line_id.request_id.action_confirm_store_credit_issued()

    def reza_action_process_exchange(self):
        self.ensure_one()
        if not self.reza_request_line_id:
            raise UserError(
                _("This legacy RMA must be linked to a Return Request before an exchange can be created.")
            )
        return self.reza_request_line_id.request_id.action_process_exchange()

    def reza_try_auto_generate_label(self):
        """Attempt label generation and retain a visible failure on the request."""
        self.ensure_one()
        if self.reza_return_method != "auspost":
            return
        if self.reza_request_line_id:
            return self.reza_request_line_id.request_id.action_retry_label()
        try:
            self._reza_generate_starshipit_return_label()
            # Pull actual shipping price from the picking if available
            picking = self._reza_get_starshipit_source_picking()
            if picking and picking.starshipit_service_price and not self.reza_return_shipping_fee:
                self.reza_return_shipping_fee = picking.starshipit_service_price
        except Exception as error:
            _logger.exception("Legacy RMA label generation failed for %s", self.name)
            self.message_post(
                body=_("Return label generation failed: %s", str(error)),
                subtype_xmlid="mail.mt_note",
            )
            self.activity_schedule(
                "mail.mail_activity_data_warning",
                summary=_("Return label generation failed"),
                note=str(error),
            )

    def reza_action_generate_return_label(self):
        self.ensure_one()
        if self.reza_return_method != "auspost":
            raise UserError(_("Return labels can only be generated for Australia Post returns."))
        if self.reza_request_line_id:
            return self.reza_request_line_id.request_id.action_retry_label()
        self._reza_generate_starshipit_return_label()
        return {"type": "ir.actions.client", "tag": "reload"}

    def reza_action_close(self):
        self.ensure_one()
        self.action_finish()
        self.reza_send_done_email()
