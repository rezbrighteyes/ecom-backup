# -- coding: utf-8 --
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    review_email_sent = fields.Boolean(string='Review Email Sent', default=False)

    def action_send_review_request(self):
        self.ensure_one()
        template = self.env.ref('reza_product_reviews.mail_template_review_request', raise_if_not_found=False)
        if not template:
            return
        template.send_mail(self.id, force_send=True)
        self.review_email_sent = True

    def _send_review_request_auto(self):
        """Called by cron — sends review request 7 days after delivery."""
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=7)
        orders = self.search([
            ('state', 'in', ['sale', 'done']),
            ('review_email_sent', '=', False),
            ('date_order', '<=', cutoff),
            ('website_id', '!=', False),
        ])
        for order in orders:
            try:
                order.action_send_review_request()
            except Exception:
                continue
