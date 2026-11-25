# -*- coding: utf-8 -*-
"""The "Storefront" section of the website form: ask for a rebuild, and see
what the storefront last published.

The website model is readable by public users (website_sale), so both new
fields carry groups: nothing here reaches a shopper over call_kw.
"""

from odoo import _, fields, models
from odoo.exceptions import AccessError

from .. import content

DESIGNER = "website.group_website_designer"


class Website(models.Model):
    _inherit = "website"

    rz_storefront_refresh_requested_at = fields.Datetime(
        string="Storefront refresh requested", readonly=True, copy=False,
        groups="base.group_user")
    rz_storefront_status = fields.Text(
        string="Storefront last published", compute="_compute_rz_storefront_status",
        groups=DESIGNER)

    def action_rz_storefront_refresh(self):
        """Button. Any signed-in user can call a public method over RPC, so
        the group is checked here, not only on the button."""
        if not self.env.su and not self.env.user.has_group(DESIGNER):
            raise AccessError(_("Only website designers can refresh the storefront."))
        self.write({"rz_storefront_refresh_requested_at": fields.Datetime.now()})
        return True

    def _compute_rz_storefront_status(self):
        for website in self:
            website.rz_storefront_status = content.build_status_text(website)
