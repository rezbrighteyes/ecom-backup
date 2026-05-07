# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_signed = fields.Boolean(string="Is Signed", compute="_compute_is_signed")

    @api.depends("signature")
    def _compute_is_signed(self):
        for picking in self:
            picking.is_signed = picking.signature

    def write(self, vals):
        res = super(SaleOrder, self).write(vals)
        if vals.get("signature"):
            for sale in self:
                sale.write(
                    {
                        "signed_by": sale.partner_id.name,
                        "signed_on": fields.Datetime.now(),
                    }
                )
                sale._attach_sign()
        return res

    def _attach_sign(self):
        """Render the report in pdf and attach it to the picking in `self`."""
        self.ensure_one()
        report = self.env["ir.actions.report"]._render_qweb_pdf(
            "sale.action_report_saleorder", self.id
        )
        filename = "%s_signed_sale_order" % self.name
        if self.partner_id:
            message = _("Order signed by %s", self.partner_id.name)
        else:
            message = _("Order signed")
        self.message_post(
            attachments=[("%s.pdf" % filename, report[0])],
            body=message,
        )
        return True
