# -*- coding: utf-8 -*-

import logging
import re

from markupsafe import Markup, escape

from odoo import _, models
from odoo.tools import html2plaintext


_logger = logging.getLogger(__name__)

PORTAL_MESSAGE_NOTIFY_EMAILS_PARAM = (
    "d3_sale_extended.portal_message_notify_emails"
)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        if not self.env.context.get("d3_skip_sale_portal_message_notification"):
            try:
                self._d3_notify_portal_sale_message(message)
            except Exception:
                _logger.exception(
                    "Unable to send sale order portal message notification."
                )
        return message

    def _d3_notify_portal_sale_message(self, message):
        self.ensure_one()
        if not self._d3_is_customer_portal_message(message):
            return

        recipients = self._d3_get_portal_message_notify_emails()
        if not recipients:
            return

        self.env["mail.mail"].sudo().create(
            self._d3_prepare_portal_message_notification_values(
                message, recipients
            )
        ).send()

    def _d3_is_customer_portal_message(self, message):
        self.ensure_one()
        if not message or message.model != self._name or message.res_id != self.id:
            return False
        if message.message_type != "comment":
            return False
        comment_subtype = self.env.ref(
            "mail.mt_comment",
            raise_if_not_found=False,
        )
        if message.subtype_id != comment_subtype:
            return False

        author = message.author_id
        if not author:
            return False
        if author.user_ids.filtered(lambda user: user.has_group("base.group_user")):
            return False

        order_partners = (
            self.partner_id
            | self.partner_invoice_id
            | self.partner_shipping_id
        )
        commercial_partner = self.partner_id.commercial_partner_id
        return (
            author in order_partners
            or author.commercial_partner_id == commercial_partner
        )

    def _d3_get_portal_message_notify_emails(self):
        parameter_keys = [PORTAL_MESSAGE_NOTIFY_EMAILS_PARAM]
        if "website_id" in self._fields and self.website_id:
            parameter_keys.insert(
                0,
                "%s.%s" % (
                    PORTAL_MESSAGE_NOTIFY_EMAILS_PARAM,
                    self.website_id.id,
                ),
            )

        config = self.env["ir.config_parameter"].sudo()
        raw_emails = ""
        for key in parameter_keys:
            raw_emails = config.get_str(key, "")
            if raw_emails:
                break

        return [
            email
            for email in re.split(r"[,;\s]+", raw_emails or "")
            if email
        ]

    def _d3_prepare_portal_message_notification_values(self, message, recipients):
        self.ensure_one()
        base_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_str("web.base.url", "")
            .rstrip("/")
        )
        backend_url = "%s/web#id=%s&model=sale.order&view_type=form" % (
            base_url,
            self.id,
        )
        message_text = html2plaintext(message.body or "").strip()
        website_name = (
            self.website_id.display_name
            if "website_id" in self._fields and self.website_id
            else ""
        )

        body = Markup(
            "<p>A customer posted a message on sale order <strong>%(order)s</strong>.</p>"
            "<ul>"
            "<li><strong>Customer:</strong> %(customer)s</li>"
            "<li><strong>Author:</strong> %(author)s</li>"
            "<li><strong>Website:</strong> %(website)s</li>"
            "</ul>"
            "<blockquote>%(message)s</blockquote>"
            "<p><a href='%(backend_url)s'>Open the sale order in Odoo</a></p>"
        ) % {
            "order": escape(self.name or ""),
            "customer": escape(self.partner_id.display_name or ""),
            "author": escape(message.author_id.display_name or ""),
            "website": escape(website_name),
            "message": escape(message_text or _("No message body.")),
            "backend_url": escape(backend_url),
        }

        email_from = (
            self.company_id.email_formatted
            or self.user_id.email_formatted
            or self.env.user.email_formatted
        )
        values = {
            "subject": _(
                "Customer message on sale order %(order)s",
                order=self.name,
            ),
            "body_html": body,
            "email_to": ",".join(recipients),
            "auto_delete": True,
        }
        if email_from:
            values["email_from"] = email_from
        if message.reply_to:
            values["reply_to"] = message.reply_to
        return values
