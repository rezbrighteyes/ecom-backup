# -- coding: utf-8 --
from odoo import api, fields, models
from odoo.tools import html_escape

NOTIFY_USER_IDS = [6, 7, 90]  # Luke, April, Reza


class ProductReview(models.Model):
    _inherit = 'rating.rating'

    is_approved = fields.Boolean(string='Approved', default=False)
    is_verified_buyer = fields.Boolean(
        string='Verified Buyer',
        compute='_compute_verified_buyer',
        store=True
    )

    @api.depends('partner_id', 'res_id', 'res_model')
    def _compute_verified_buyer(self):
        for review in self:
            if review.res_model != 'product.template' or not review.partner_id:
                review.is_verified_buyer = False
                continue
            purchased = self.env['sale.order.line'].sudo().search_count([
                ('product_id.product_tmpl_id', '=', review.res_id),
                ('order_id.partner_id', '=', review.partner_id.id),
                ('order_id.state', 'in', ['sale', 'done']),
            ])
            review.is_verified_buyer = bool(purchased)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.res_model == 'product.template':
                if record.message_id:
                    record.message_id.sudo().write({'is_internal': True})
                record._notify_review_team()
        return records

    def action_approve(self):
        self.is_approved = True
        if self.message_id:
            self.message_id.sudo().write({'is_internal': False})

    def action_reject(self):
        self.is_approved = False
        self.unlink()

    def _notify_review_team(self):
        self.ensure_one()
        product = self.env['product.template'].sudo().browse(self.res_id)
        users = self.env['res.users'].sudo().browse(NOTIFY_USER_IDS).exists()
        partner_ids = users.mapped('partner_id').ids

        # Get correct website URL
        website = self.env['website'].sudo().search([
            ('id', '=', product.website_id.id)
        ], limit=1) if product.website_id else self.env['website'].sudo().browse(4)
        base_url = website.domain or self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        product_url = '%s%s' % (base_url.rstrip('/'), product.website_url)

        body = """
<p>A new review has been submitted and is waiting for your approval.</p>
<ul>
    <li><strong>Product:</strong> %s</li>
    <li><strong>Customer:</strong> %s</li>
    <li><strong>Rating:</strong> %s/5</li>
    <li><strong>Review:</strong> %s</li>
</ul>
<p>Please go to the <strong>eCommerce &rarr; Reviews</strong> section to approve or reject this review.</p>
<p><a href="%s">View Product</a></p>
""" % (
            html_escape(product.name),
            html_escape(self.partner_id.name or 'Anonymous'),
            int(self.rating),
            html_escape(self.feedback or ''),
            product_url,
        )

        product.sudo().message_notify(
            partner_ids=partner_ids,
            body=body,
            subject='New Review: %s' % product.name,
            author_id=self.env.ref('base.partner_root').id,
            email_layout_xmlid=False,
            force_send=False,
        )