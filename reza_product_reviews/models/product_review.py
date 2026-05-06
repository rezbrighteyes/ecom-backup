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

        body = '<p>New review for <b>%s</b> by <b>%s</b> &mdash; %s/5</p><p>"%s"</p><p><a href="/odoo/website/reviews">Go to Reviews &rarr;</a> to approve or reject.</p>' % (
            html_escape(product.name),
            html_escape(self.partner_id.name or 'Anonymous'),
            int(self.rating),
            html_escape(self.feedback or ''),
        )

        # Post to dedicated Product Reviews channel
        channel = self.env.ref(
            'reza_product_reviews.channel_product_reviews',
            raise_if_not_found=False
        )
        if channel:
            channel.sudo().message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
        else:
            # Fallback — notify directly
            users = self.env['res.users'].sudo().browse(NOTIFY_USER_IDS).exists()
            partner_ids = [(4, uid) for uid in users.mapped('partner_id').ids]
            self.env['mail.message'].sudo().with_context(mail_notify_author=True).create({
                'message_type': 'notification',
                'subtype_id': self.env.ref('mail.mt_comment').id,
                'body': body,
                'subject': 'New Review: %s' % product.name,
                'partner_ids': partner_ids,
                'author_id': self.env.ref('base.partner_root').id,
                'model': False,
                'res_id': False,
            })