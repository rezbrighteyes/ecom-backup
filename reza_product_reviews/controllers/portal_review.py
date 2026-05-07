# -- coding: utf-8 --
from odoo import http
from odoo.addons.portal_rating.controllers import portal_chatter as base


class PortalChatter(base.PortalChatter):

    def portal_message_fetch(self, thread_model, thread_id, limit=10, after=None, before=None, **kw):
        res = super().portal_message_fetch(thread_model, thread_id, limit=limit, after=after, before=before, **kw)

        if thread_model == 'product.template':
            unapproved = http.request.env['rating.rating'].sudo().search([
                ('res_model', '=', 'product.template'),
                ('res_id', '=', thread_id),
                ('is_approved', '=', False),
                ('message_id', '!=', False),
            ])
            unapproved_msg_ids = set(unapproved.mapped('message_id').ids)

            if unapproved_msg_ids and 'messages' in res:
                # res['messages'] is a list of dicts in Odoo 18; compare by id key
                res['messages'] = [
                    m for m in res['messages']
                    if (m.get('id') if isinstance(m, dict) else m) not in unapproved_msg_ids
                ]

            # Recompute rating stats using approved reviews only — the base
            # controller queries rating.rating directly and ignores is_approved
            if 'rating_stats' in res:
                approved = http.request.env['rating.rating'].sudo().search([
                    ('res_model', '=', 'product.template'),
                    ('res_id', '=', int(thread_id)),
                    ('is_approved', '=', True),
                    ('consumed', '=', True),
                    ('rating', '>=', 1),
                ])
                total = len(approved)
                avg = sum(r.rating for r in approved) / total if total else 0.0
                counts = {i: 0 for i in range(1, 6)}
                for r in approved:
                    counts[min(5, max(1, int(round(r.rating))))] += 1
                res['rating_stats'] = {
                    'avg': avg,
                    'total': total,
                    'percent': {i: (counts[i] / total * 100) if total else 0.0 for i in range(1, 6)},
                }

        return res
