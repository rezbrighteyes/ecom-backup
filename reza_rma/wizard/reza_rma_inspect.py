from odoo import fields, models
from odoo.exceptions import UserError


class RezaRmaInspectWizard(models.TransientModel):
    _name = "reza.rma.inspect.wizard"
    _description = "RMA Inspection Wizard"

    rma_id = fields.Many2one(comodel_name="rma", string="RMA", required=True)
    inspection_outcome = fields.Selection(
        [
            ("acceptable", "Acceptable — Condition Met"),
            ("damaged_used", "Damaged / Used — Return to Customer"),
            ("missing_packaging", "Missing Original Packaging"),
        ],
        string="Inspection Outcome",
        required=True,
    )
    inspection_notes = fields.Text(string="Inspection Notes")
    disposition = fields.Selection(
        [
            ("restock", "Restock"),
            ("refurbish", "Refurbish"),
            ("quarantine", "Quarantine"),
            ("discard", "Discard"),
            ("return_customer", "Return to Customer"),
        ],
        required=True,
    )

    def action_confirm(self):
        self.ensure_one()
        if self.rma_id.state not in ("received", "refunded", "replaced", "finished"):
            raise UserError("The returned item must be received before inspection.")
        self.rma_id.write({
            "reza_inspection_outcome": self.inspection_outcome,
            "reza_inspection_notes": self.inspection_notes,
        })
        if self.rma_id.reza_request_line_id:
            self.rma_id.reza_request_line_id.write(
                {
                    "inspection_outcome": (
                        "pass" if self.inspection_outcome == "acceptable" else "fail"
                    ),
                    "inspection_notes": self.inspection_notes,
                    "disposition": self.disposition,
                }
            )
            request = self.rma_id.reza_request_line_id.request_id
            request.state = (
                "resolution_pending"
                if all(line.inspection_outcome == "pass" for line in request.line_ids)
                else "inspection_due"
            )
        if self.inspection_outcome in ("damaged_used", "missing_packaging"):
            self.rma_id.action_cancel()
            self.rma_id.reza_send_damaged_email()
        return {"type": "ir.actions.act_window_close"}
