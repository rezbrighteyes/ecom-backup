from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.reza_rma.controllers.portal import RezaRmaPortal


@tagged("post_install", "-at_install")
class TestRezaRmaFlow(TransactionCase):
    """A delivered website order is returned through the reza_rma request
    flow: grouped request -> OCA RMA -> receipt -> inspection -> credit note."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.website = cls.env["website"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        Operation = cls.env["rma.operation"]
        cls.refund_op = Operation.create({
            "name": "Reza test refund",
            "action_create_receipt": "automatic_on_confirm",
            "action_create_refund": "manual_after_receipt",
            "action_create_delivery": False,
        })
        cls.exchange_op = Operation.create({
            "name": "Reza test exchange",
            "action_create_receipt": "automatic_on_confirm",
            "action_create_refund": False,
            "action_create_delivery": "manual_after_receipt",
        })
        cls.income = cls.env["account.account"].create({
            "name": "Reza RMA test income",
            "code": "RZRMA1",
            "account_type": "income",
        })
        cls.fee_product = cls.env["product.product"].create({
            "name": "Return shipping charge",
            "type": "service",
            "property_account_income_id": cls.income.id,
            "taxes_id": [(5, 0, 0)],
        })
        cls.company.write({
            "reza_rma_refund_operation_id": cls.refund_op.id,
            "reza_rma_exchange_operation_id": cls.exchange_op.id,
            "reza_rma_return_shipping_product_id": cls.fee_product.id,
            "reza_rma_return_shipping_fee": 9.95,
            "reza_rma_return_window_days": 30,
            "reza_rma_enable_labels": False,
            "reza_rma_enable_refunds": True,
        })
        cls.reason = cls.env.ref("reza_rma.reason_change_of_mind")
        cls.reason.write({"allowed_resolution": "any", "reza_return_fee_waived": False})
        cls.product = cls.env["product.product"].create({
            "name": "Reza RMA sunglasses",
            "type": "consu",
            "is_storable": True,
            "list_price": 50.0,
            "property_account_income_id": cls.income.id,
            "taxes_id": [(5, 0, 0)],
        })
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 10
        )
        cls.partner = cls.env["res.partner"].create({
            "name": "Reza RMA customer",
            "email": "rma.customer@example.com",
            "street": "1 Test St",
            "city": "Brisbane",
            "zip": "4000",
            "country_id": cls.env.ref("base.au").id,
        })
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.partner.id,
            "website_id": cls.website.id,
            "warehouse_id": cls.warehouse.id,
            "order_line": [(0, 0, {
                "product_id": cls.product.id,
                "product_uom_qty": 2,
                "price_unit": 50.0,
                "tax_ids": [(5, 0, 0)],
            })],
        })
        cls.order.action_confirm()
        cls.delivery = cls.order.picking_ids
        for move in cls.delivery.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        cls.delivery.button_validate()
        cls.line = cls.order.order_line

    def _create_request(self, quantity=1, operation_type="credit_note", seed="seed-1"):
        # MockRequest's httprequest has no real headers; the IP hash is a
        # privacy detail, not what these tests check.
        with MockRequest(self.env, website=self.website), patch.object(
            RezaRmaPortal, "_reza_get_ip_hash", return_value="test-ip-hash"
        ):
            return RezaRmaPortal()._reza_create_grouped_request(
                self.order,
                [{"line": self.line, "quantity": quantity, "reason": self.reason,
                  "notes": "Too big"}],
                operation_type,
                return_method="manual",
                idempotency_seed=seed,
            )

    def _receive(self, grouped_request):
        receipt = grouped_request.receipt_picking_id
        for move in receipt.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        receipt.button_validate()
        return receipt

    def _inspect(self, rma, outcome="acceptable"):
        wizard = self.env["reza.rma.inspect.wizard"].create({
            "rma_id": rma.id,
            "inspection_outcome": outcome,
            "disposition": "restock",
        })
        wizard.action_confirm()

    def test_delivered_order_is_fully_delivered(self):
        self.assertEqual(self.delivery.state, "done")
        self.assertEqual(self.line.qty_delivered, 2)

    def test_request_creates_confirmed_rma_with_receipt(self):
        grouped_request = self._create_request()
        self.assertEqual(grouped_request.sale_order_id, self.order)
        self.assertEqual(grouped_request.website_id, self.website)
        self.assertEqual(grouped_request.return_shipping_fee, 9.95)
        self.assertEqual(grouped_request.label_state, "manual")
        self.assertEqual(len(grouped_request.line_ids), 1)
        rma = grouped_request.rma_ids
        self.assertEqual(len(rma), 1)
        self.assertEqual(rma.state, "confirmed")
        self.assertEqual(rma.operation_id, self.refund_op)
        self.assertEqual(rma.order_id, self.order)
        self.assertEqual(rma.move_id, self.delivery.move_ids)
        self.assertEqual(rma.product_uom_qty, 1)
        self.assertEqual(rma.reza_request_line_id, grouped_request.line_ids)
        receipt = grouped_request.receipt_picking_id
        self.assertTrue(receipt)
        self.assertEqual(receipt.picking_type_code, "incoming")
        self.assertEqual(receipt.move_ids.product_id, self.product)
        self.assertEqual(receipt.move_ids.product_uom_qty, 1)
        self.assertEqual(receipt.move_ids.origin_returned_move_id, self.delivery.move_ids)
        self.assertEqual(receipt.move_ids.rma_receiver_ids, rma)

    def test_same_seed_returns_the_same_request(self):
        first = self._create_request(seed="same")
        second = self._create_request(seed="same")
        self.assertEqual(first, second)
        self.assertEqual(
            self.env["reza.rma.request"].search_count([("sale_order_id", "=", self.order.id)]), 1
        )

    def test_cannot_return_more_than_delivered(self):
        self._create_request(quantity=2, seed="all")
        with self.assertRaises(ValidationError) as cm:
            self._create_request(quantity=1, seed="more")
        self.assertIn("no longer available", str(cm.exception))

    def test_return_is_received_inspected_and_credited(self):
        grouped_request = self._create_request()
        rma = grouped_request.rma_ids
        self._receive(grouped_request)
        self.assertEqual(rma.state, "received")
        self.assertTrue(rma.reza_warehouse_received_date)
        self.assertEqual(grouped_request.state, "inspection_due")
        self.assertEqual(self.line.qty_delivered, 2,
                         "a manual-refund operation must not lower the delivered quantity")

        self._inspect(rma)
        self.assertEqual(grouped_request.line_ids.inspection_outcome, "pass")
        self.assertEqual(grouped_request.state, "resolution_pending")

        grouped_request.action_process_refund()
        request_line = grouped_request.line_ids
        credit_note = request_line.credit_note_id
        self.assertTrue(credit_note)
        self.assertEqual(credit_note.move_type, "out_refund")
        self.assertEqual(credit_note.state, "draft")
        self.assertEqual(rma.state, "refunded")
        self.assertEqual(request_line.payment_refund_state, "manual_required")
        product_line = credit_note.invoice_line_ids.filtered(
            lambda l: l.product_id == self.product
        )
        fee_line = credit_note.invoice_line_ids.filtered(
            lambda l: l.reza_rma_request_id == grouped_request
        )
        self.assertEqual(product_line.quantity, 1)
        self.assertAlmostEqual(product_line.price_unit, 50.0)
        self.assertEqual(fee_line.product_id, self.fee_product)
        self.assertAlmostEqual(fee_line.price_unit, -9.95)
        self.assertAlmostEqual(credit_note.amount_total, 40.05)
        # A second run does not add the charge again.
        grouped_request._add_return_shipping_charge()
        self.assertEqual(
            len(credit_note.invoice_line_ids.filtered(
                lambda l: l.reza_rma_request_id == grouped_request)), 1
        )

    def test_refund_refused_before_inspection(self):
        grouped_request = self._create_request()
        self._receive(grouped_request)
        with self.assertRaises(UserError) as cm:
            grouped_request.action_process_refund()
        self.assertIn("pass inspection", str(cm.exception))
        self.assertFalse(grouped_request.line_ids.credit_note_id)

    def test_refund_refused_while_disabled(self):
        self.company.reza_rma_enable_refunds = False
        grouped_request = self._create_request()
        self._receive(grouped_request)
        self._inspect(grouped_request.rma_ids)
        with self.assertRaises(UserError) as cm:
            grouped_request.action_process_refund()
        self.assertIn("disabled", str(cm.exception))

    def test_failed_inspection_hits_known_cancel_defect(self):
        # KNOWN DEFECT, same on Odoo 18 (stock_move._action_cancel raises the
        # same error there): a failed inspection calls rma.action_cancel(),
        # which cancels the reception move, but inspection is only allowed
        # once that move is done. So a failed inspection always raises and
        # the request transaction is rolled back. Pinned here so a fix shows.
        grouped_request = self._create_request()
        rma = grouped_request.rma_ids
        self._receive(grouped_request)
        with self.assertRaises(UserError) as cm:
            self._inspect(rma, outcome="damaged_used")
        self.assertIn("cannot cancel a stock move", str(cm.exception))

    def test_inspection_refused_before_receipt(self):
        grouped_request = self._create_request()
        with self.assertRaises(UserError) as cm:
            self._inspect(grouped_request.rma_ids)
        self.assertIn("must be received", str(cm.exception))

    def test_automatic_refund_operation_is_refused(self):
        with self.assertRaises(ValidationError) as cm:
            self.refund_op.action_create_refund = "automatic_after_receipt"
        self.assertIn("Automatic RMA refunds are disabled", str(cm.exception))

    def test_portal_counter_and_rma_portal_wizard(self):
        controller = RezaRmaPortal()
        with MockRequest(self.env(user=self.env.ref("base.user_admin")), website=self.website):
            model, domain, access = controller._prepare_portal_counter_values("reza_rma_count")
        self.assertEqual((model, access), ("reza.rma.request", "sudo"))
        self.assertIn(("website_id", "=", self.website.id), domain)
        # The OCA RMA home card is repurposed as the "Returns" card.
        entry = self.env.ref("rma.portal_entry_rma")
        self.assertEqual(entry.placeholder_count, "reza_rma_count")
        self.assertEqual(entry.url, "/my/rmas")
