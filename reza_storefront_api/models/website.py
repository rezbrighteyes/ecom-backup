# -*- coding: utf-8 -*-
"""The "Storefront" section of the website form: ask for a rebuild, and see
what the storefront last published.

The website model is readable by public users (website_sale), so every new
field carries groups: nothing here reaches a shopper over call_kw.
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

    rz_storefront_use_odoo_menu = fields.Boolean(
        string="Use the Odoo menu", copy=False, groups=DESIGNER,
        help="Off: the storefront builds its menus from the shop categories, as "
             "before. On: it shows this website's Odoo menu (Website > Site > Menu "
             "Editor), drawn as set in \"Edit storefront menu\".")
    rz_storefront_featured_brand_ids = fields.One2many(
        "reza.storefront.featured.brand", "website_id", string="Featured brands",
        groups=DESIGNER,
        help="Brand tiles of the storefront Brands menu, in this order. Empty: the "
             "six brands with the most products.")

    def _rz_check_designer(self):
        if not self.env.su and not self.env.user.has_group(DESIGNER):
            raise AccessError(_("Only website designers can change the storefront."))

    def action_rz_storefront_menu(self):
        """Button: this website's menu items, with the storefront columns. The
        core Menus list is debug-only, so the Storefront tab opens this one."""
        self._rz_check_designer()
        self.ensure_one()
        root = self.menu_id
        return {
            "type": "ir.actions.act_window",
            "name": _("Storefront menu: %s", self.name),
            "res_model": "website.menu",
            "view_mode": "list,form",
            "views": [(self.env.ref("reza_storefront_api.rz_storefront_menu_list").id, "list"),
                      (False, "form")],
            "domain": [("website_id", "=", self.id), ("parent_id", "!=", False)],
            "context": {"default_website_id": self.id, "default_parent_id": root.id},
            "target": "current",
        }

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
