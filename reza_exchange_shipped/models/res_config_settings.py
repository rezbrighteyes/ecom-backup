# -*- coding: utf-8 -*-
from odoo import fields, models

from .customer_refund import DEFAULT_ALERT_EMAILS


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    reza_refund_auto = fields.Boolean(
        "Send refunds through Odoo",
        config_parameter="reza_exchange_shipped.refund_auto",
        help="On: Refund (shipped) sends a Stripe refund from Odoo itself. "
        "Off: the refund user gets a task and does the refund in Stripe or PayPal. "
        "PayPal is always by hand. Either way, a daily check confirms the money went back.")
    reza_refund_user_id = fields.Many2one(
        "res.users", string="Refunds done by",
        config_parameter="reza_exchange_shipped.refund_user_id",
        domain="[('share', '=', False)]",
        help="Who gets the 'Refund $X' task. Empty: Accounts Dept.")
    reza_refund_alert_emails = fields.Char(
        "Also alert",
        config_parameter="reza_exchange_shipped.refund_alert_emails",
        default=DEFAULT_ALERT_EMAILS,
        help="Comma-separated emails that hear, with the refund user, when a refund is "
        "late (3 days) or for a different amount.")
