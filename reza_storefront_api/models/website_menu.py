# -*- coding: utf-8 -*-
"""How the static storefront renders an Odoo website menu item.

Staff edit the menu in Odoo's own per-website menu (name, link, order,
nesting); these fields only say how the storefront draws each top item and
which badge it carries. The storefront reads the menu only when the website's
"Use the Odoo menu" switch is on (website.rz_storefront_use_odoo_menu).

Access: core ACLs already let only website designers write website.menu, and
public users read it (Odoo renders it on every page). These fields are drawn
on the public storefront anyway, so they carry no groups.

Links are NOT constrained here: Odoo's own editor writes "#", mailto: and
page links into url. The export (menu.py) applies the storefront's link rule
and leaves out what fails it.
"""

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

KINDS = [
    ("link", "Link"),
    ("category_mega", "Category menu"),
    ("brands_mega", "Brands menu"),
    ("drop", "Short list (its sub-menus)"),
]
BADGE_STYLES = [("promo", "Promo"), ("new", "New"), ("sale", "Sale")]
BADGE_MAX = 24
_BADGE_BAD = re.compile(r"[\x00-\x1f\x7f<>]")


class WebsiteMenu(models.Model):
    _inherit = "website.menu"

    rz_kind = fields.Selection(
        KINDS, string="Storefront display", required=True, default="link",
        help="How the storefront draws this top menu item. Link: a plain link. "
             "Category menu: the category's styles and brands panel. Brands menu: "
             "the brand search, A to Z and featured brand tiles. Short list: a "
             "small drop-down of this item's sub-menus.")
    rz_badge = fields.Char(
        string="Storefront badge", help="Short text in a pill next to the item, "
        "for example \"Up to 75%%\". %s characters at most." % BADGE_MAX)
    rz_badge_style = fields.Selection(BADGE_STYLES, string="Badge style", default="promo")
    rz_public_categ_id = fields.Many2one(
        "product.public.category", string="Storefront category", ondelete="set null",
        help="Category menu only: the category whose panel is shown.")

    @api.constrains("rz_badge")
    def _check_rz_badge(self):
        for menu in self:
            badge = menu.rz_badge or ""
            if len(badge) > BADGE_MAX:
                raise ValidationError(_("The storefront badge is longer than %s characters.",
                                        BADGE_MAX))
            if badge and (_BADGE_BAD.search(badge) or not badge.strip()):
                raise ValidationError(_("The storefront badge holds characters it cannot show."))

    @api.constrains("rz_kind", "rz_public_categ_id")
    def _check_rz_kind(self):
        for menu in self:
            if menu.rz_kind == "category_mega" and not menu.rz_public_categ_id:
                raise ValidationError(_("A category menu needs its storefront category."))
            if menu.rz_kind != "category_mega" and menu.rz_public_categ_id:
                raise ValidationError(_("Only a category menu takes a storefront category."))
