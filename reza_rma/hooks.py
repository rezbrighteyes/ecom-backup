import hashlib

from odoo import fields


def post_init_hook(env):
    operations = env["rma.operation"].search([])
    operations.write(
        {
            "auto_confirm_reception": False,
        }
    )
    operations.filtered(
        lambda operation: operation.action_create_delivery
        in ("automatic_on_confirm", "automatic_after_receipt")
    ).write({"action_create_delivery": "manual_after_receipt"})
    operations.filtered(
        lambda operation: operation.action_create_refund
        in ("automatic_on_confirm", "automatic_after_receipt", "update_quantity")
    ).write({"action_create_refund": "manual_after_receipt"})

    Request = env["reza.rma.request"]
    RequestLine = env["reza.rma.request.line"]
    for rma in env["rma"].search([("reza_request_line_id", "=", False)]):
        order = rma.order_id
        sale_line = rma.sale_line_id
        website = order.website_id if order else False
        if (
            not order
            or not sale_line
            or not website
            or website.company_id != rma.company_id
            or not rma.partner_id
            or not rma.product_id
            or not rma.product_uom
            or not rma.reza_reason_id
            or rma.product_uom_qty <= 0
            or rma.product_uom_qty > sale_line.qty_delivered
            or (
                sum(
                    RequestLine.search(
                        [
                            ("sale_order_line_id", "=", sale_line.id),
                            ("request_id.state", "not in", ["cancelled"]),
                        ]
                    ).mapped("quantity")
                )
                + rma.product_uom_qty
                > sale_line.qty_delivered
            )
        ):
            rma.reza_migration_review_required = True
            continue
        key = hashlib.sha256(f"legacy-rma:{rma.id}".encode()).hexdigest()
        grouped_request = Request.create(
            {
                "name": f"LEGACY/{rma.name}",
                "company_id": rma.company_id.id,
                "website_id": website.id,
                "partner_id": rma.partner_id.id,
                "sale_order_id": order.id,
                "state": "migration_review" if not rma.move_id or not rma.picking_id else "requested",
                "idempotency_key": key,
                "policy_version": "legacy",
                "policy_text_snapshot": "Legacy RMA backfill; customer policy acceptance not captured.",
                "policy_accepted_at": rma.create_date or fields.Datetime.now(),
                "currency_id": order.currency_id.id,
                "return_shipping_fee": rma.reza_return_shipping_fee,
                "label_state": "ready" if rma.reza_return_label_attachment_id else "pending",
                "label_attachment_id": rma.reza_return_label_attachment_id.id,
                "carrier_tracking_ref": rma.reza_return_tracking_ref,
                "migration_review_required": not rma.move_id or not rma.picking_id,
            }
        )
        request_line = RequestLine.create(
            {
                "request_id": grouped_request.id,
                "rma_id": rma.id,
                "sale_order_line_id": sale_line.id,
                "source_move_id": rma.move_id.id,
                "product_id": rma.product_id.id,
                "uom_id": rma.product_uom.id,
                "quantity": rma.product_uom_qty,
                "reason_id": rma.reza_reason_id.id,
                "resolution": {
                    "credit_note": "refund",
                    "store_credit": "store_credit",
                    "exchange": "exchange",
                }.get(rma.reza_operation_type, "refund"),
                "credit_note_id": rma.refund_id.id,
                "credit_note_line_id": rma.refund_line_id.id,
                "resolution_idempotency_key": f"{key}:{sale_line.id}",
            }
        )
        rma.reza_request_line_id = request_line
