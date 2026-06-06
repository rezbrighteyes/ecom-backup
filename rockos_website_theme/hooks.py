import logging
import base64

from odoo import tools


_logger = logging.getLogger(__name__)

ROCKOS_WEBSITE_NAME = "Rockos"
ROCKOS_BRANCH_NAME = "Rockos"
ROCKOS_PARENT_COMPANY_NAME = "ECOM SUPERSTORE PTY LTD"
ROCKOS_VIEW_PREFIX = "rockos_website_theme."


def _get_or_create_rockos_branch(env):
    Company = env["res.company"].sudo().with_context(active_test=False)
    parent = Company.search(
        [("name", "=", ROCKOS_PARENT_COMPANY_NAME), ("parent_id", "=", False)],
        limit=1,
    ) or env.company

    branch = Company.search([
        ("name", "=", ROCKOS_BRANCH_NAME),
        ("parent_id", "=", parent.id),
    ], limit=1)
    if branch:
        if not branch.active:
            branch.active = True
        return branch

    branch = Company.create({
        "name": ROCKOS_BRANCH_NAME,
        "parent_id": parent.id,
    })
    _logger.info(
        "Created Rockos company branch id=%s under company id=%s",
        branch.id,
        parent.id,
    )
    return branch


def _get_or_create_rockos_website(env, branch):
    Website = env["website"].sudo()
    website = Website.search([("name", "=", ROCKOS_WEBSITE_NAME)], limit=1)
    if website:
        if website.company_id != branch:
            website.company_id = branch.id
        return website

    website = Website.create({
        "name": ROCKOS_WEBSITE_NAME,
        "company_id": branch.id,
        "domain": False,
        "configurator_done": True,
    })
    _logger.info("Created isolated Rockos website id=%s", website.id)
    return website


def _scope_views_to_rockos(env, website):
    views = env["ir.ui.view"].sudo().with_context(active_test=False).search([
        ("key", "like", ROCKOS_VIEW_PREFIX),
        ("type", "=", "qweb"),
    ])
    views.filtered(lambda view: view.website_id != website).write({
        "website_id": website.id,
    })
    _logger.info("Scoped %d Rockos views to website id=%s", len(views), website.id)


def _configure_rockos_website(env, website):
    values = {
        "rockos_facebook_url": website.rockos_facebook_url
        or "https://www.facebook.com/rockosaustralia/",
        "rockos_instagram_url": website.rockos_instagram_url
        or "https://www.instagram.com/rockos_australia",
        "rockos_phone": website.rockos_phone or "0754991191",
        "rockos_free_shipping_text": website.rockos_free_shipping_text
        or "On Selected Retail Orders",
        "configurator_done": True,
    }
    if not website.logo:
        with tools.file_open(
            "rockos_website_theme/static/src/img/website_logo.png",
            "rb",
        ) as logo_file:
            values["logo"] = base64.b64encode(logo_file.read())
    website.write(values)

    root_menu = env["website.menu"].sudo().search([
        ("website_id", "=", website.id),
        ("parent_id", "=", False),
    ], limit=1)
    if root_menu:
        existing = env["website.menu"].sudo().search([
            ("website_id", "=", website.id),
            ("parent_id", "=", root_menu.id),
        ])
        wanted = [
            ("Shop", "/shop"),
            ("Returns", "/returns"),
            ("Contact Us", "/contactus"),
        ]
        for sequence, (name, url) in enumerate(wanted, start=10):
            menu = existing.filtered(lambda item: item.url == url)[:1]
            if menu:
                menu.write({"name": name, "sequence": sequence})
            else:
                env["website.menu"].sudo().create({
                    "name": name,
                    "url": url,
                    "parent_id": root_menu.id,
                    "website_id": website.id,
                    "sequence": sequence,
                })


def _setup(env):
    branch = _get_or_create_rockos_branch(env)
    website = _get_or_create_rockos_website(env, branch)
    _scope_views_to_rockos(env, website)
    _configure_rockos_website(env, website)


def post_init_hook(env):
    _setup(env)


def post_update_hook(env):
    _setup(env)
