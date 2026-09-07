# -*- coding: utf-8 -*-
"""Install/uninstall hooks for the front-end menu entry.

Why a hook rather than a data file:

`website.menu` with `website_id = False` is a **template** tree, not a shared menu.
Verified on this database — menu id 1 "Default Main Menu" holds no website, while every
live site roots at its own record (Mangrove Jacks at id 27, ecomsuperstore at 10, and so
on). Odoo copies the template tree only when a *new* website is created, so a static
record parented to `website.main_menu` would appear on **none** of the 7 existing sites.

The roots are runtime records, so they cannot be referenced from static XML. This walks
the websites and adds the entry under each real root instead.
"""
import logging

_logger = logging.getLogger(__name__)

MENU_NAME = "Stockists"
MENU_URL = "/stockists"


def _root_menu(env, website):
    return env["website.menu"].search([
        ("website_id", "=", website.id),
        ("parent_id", "=", False),
    ], limit=1)


def post_init_hook(env):
    """Add a Stockists entry to every existing website's menu."""
    Menu = env["website.menu"]
    created = 0
    for website in env["website"].search([]):
        root = _root_menu(env, website)
        if not root:
            _logger.warning(
                "website_stockist: website %s (id %s) has no root menu; "
                "skipping its Stockists entry.", website.name, website.id,
            )
            continue
        existing = Menu.search([
            ("website_id", "=", website.id),
            ("url", "=", MENU_URL),
        ], limit=1)
        if existing:
            continue
        Menu.create({
            "name": MENU_NAME,
            "url": MENU_URL,
            "parent_id": root.id,
            "website_id": website.id,
            "sequence": 65,
        })
        created += 1
    _logger.info("website_stockist: created %s Stockists menu entries.", created)


def uninstall_hook(env):
    """Remove the entries the hook created.

    They were created in code rather than as XML data, so Odoo will not clean them
    up on uninstall and they would linger as menu items pointing at a dead route.
    Only exact `/stockists` URLs are touched; anything a user renamed or repointed
    is left alone.
    """
    menus = env["website.menu"].search([("url", "=", MENU_URL)])
    _logger.info("website_stockist: removing %s Stockists menu entries.", len(menus))
    menus.unlink()
