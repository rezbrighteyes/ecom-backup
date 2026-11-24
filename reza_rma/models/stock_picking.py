from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    reza_rma_request_id = fields.Many2one("reza.rma.request", copy=False, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        for picking in pickings.filtered(lambda record: record.sale_id.reza_rma_request_id):
            picking.reza_rma_request_id = picking.sale_id.reza_rma_request_id
        return pickings

    def button_validate(self):
        for picking in self:
            request = picking.reza_rma_request_id or picking.sale_id.reza_rma_request_id
            if not request or picking.picking_type_id.code != "outgoing":
                continue
            if not picking.reza_rma_request_id:
                picking.reza_rma_request_id = request
            request._ensure_resolution_allowed("exchange")
            unpaid = request.line_ids.filtered(
                lambda line: line.exchange_difference > 0
                and (
                    not line.payment_transaction_id
                    or line.payment_transaction_id.state != "done"
                )
            )
            if unpaid:
                raise UserError(
                    _("This exchange cannot be dispatched until the required payment is complete.")
                )
        result = super().button_validate()
        self.mapped("reza_rma_request_id")._update_resolution_state()
        return result
