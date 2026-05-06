# -- coding: utf-8 --
from odoo import http
from odoo.osv import expression
from odoo.addons.portal_rating.controllers import portal_chatter as base


class PortalChatter(base.PortalChatter):

    def portal_message_fetch(self, thread_model, thread_id, limit=10, after=None, before=None, **kw):
        res = super().portal_message_fetch(thread_model, thread_id, limit=limit, after=after, before=before, **kw)

        if thread_model == 'product.template':
            # Get unapproved rating message IDs
            unapproved = http.request.env['rating.rating'].sudo().search([
                ('res_model', '=', 'product.template'),
                ('res_id', '=', thread_id),
                ('is_approved', '=', False),
                ('message_id', '!=', False),
            ])
            unapproved_msg_ids = set(unapproved.mapped('message_id').ids)

            if unapproved_msg_ids and 'messages' in res:
                res['messages'] = [m for m in res['messages'] if m not in unapproved_msg_ids]

        return res