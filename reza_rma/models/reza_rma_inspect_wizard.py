from odoo import _, fields, models
from odoo.exceptions import UserError


class RezaRmaInspectWizard(models.TransientModel):
    _name = "reza.rma.inspect.wizard"
    _description = "RMA Inspection Wizard"

    rma_id = fields.Many2one(
        comodel_name="rma",
        string="RMA",
        readonly=True,
        required=True,
    )
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

    def action_confirm(self):
        self.ensure_one()
        if not self.rma_id:
            raise UserError(_("No RMA linked to this inspection."))
        self.rma_id.write({
            "reza_inspection_outcome": self.inspection_outcome,
            "reza_inspection_notes": self.inspection_notes or "",
        })
        return {"type": "ir.actions.act_window_close"}
