import logging
import base64

from odoo import tools


_logger = logging.getLogger(__name__)

ROCKOS_WEBSITE_NAME = "Rockos"
ROCKOS_BRANCH_NAME = "Rockos"
ROCKOS_PARENT_COMPANY_NAME = "ECOM SUPERSTORE PTY LTD"
ROCKOS_VIEW_PREFIX = "rockos_website_theme."
ROCKOS_MENU_VERSION = "2"
ROCKOS_PAGES = [
    ("About Us", "/about-us", "rockos_website_theme.rockos_about_us"),
    ("Returns Policy", "/returns-policy", "rockos_website_theme.rockos_returns_policy"),
    ("Shipping Policy", "/shipping", "rockos_website_theme.rockos_shipping_policy"),
    ("Privacy Policy", "/privacy-policy", "rockos_website_theme.rockos_privacy_policy"),
    ("Security Policy", "/security-policy", "rockos_website_theme.rockos_security_policy"),
    ("Expression of Interest", "/form/expression-of-interest", "rockos_website_theme.rockos_expression_interest"),
    ("Footwear Sizing Chart", "/footwear-sizing-chart", "rockos_website_theme.rockos_footwear_sizing"),
    ("Australian Melanoma Research Foundation", "/amrf", "rockos_website_theme.rockos_amrf"),
]
ROCKOS_MENU_TREE = [
    ("Thongs", "/shop?search=thongs", [
        ("Double Pluggers", "/shop?search=double+pluggers"),
        ("Nobby Thongs", "/shop?search=nobby+thongs"),
        ("Tread Thongs", "/shop?search=tread+thongs"),
        ("Kids Thongs", "/shop?search=kids+thongs"),
        ("Slides", "/shop?search=slides"),
    ]),
    ("Hats", "/shop?search=hats", [
        ("Caps", "/shop?search=caps"),
        ("Trucker Caps", "/shop?search=trucker+cap"),
        ("Bucket Hats", "/shop?search=bucket+hat"),
        ("Straw Hats", "/shop?search=straw+hat"),
        ("Beanies", "/shop?search=beanie"),
    ]),
    ("Sunnies", "/shop?search=sunglasses", [
        ("Polarised Sunglasses", "/shop?search=polarised"),
        ("Safety Glasses", "/shop?search=safety+glasses"),
        ("Readers", "/shop?search=readers"),
    ]),
    ("Technology", "/shop?search=technology", [
        ("Audio", "/shop?search=audio"),
        ("Cables & Chargers", "/shop?search=cables"),
        ("Power Banks", "/shop?search=power+bank"),
        ("Phone Accessories", "/shop?search=phone"),
    ]),
    ("Toys", "/shop?search=toys", [
        ("Die Cast", "/shop?search=die+cast"),
        ("Mini Mates", "/shop?search=mini+mates"),
        ("Nature Tubes", "/shop?search=nature+tubes"),
        ("Party Games", "/shop?search=party+games"),
    ]),
    ("Outdoor", "/shop?search=outdoor", [
        ("Beach", "/shop?search=beach"),
        ("Fishing", "/shop?search=fishing"),
        ("Goggles", "/shop?search=goggles"),
        ("Outdoor Games", "/shop?search=outdoor+games"),
    ]),
    ("Games", "/shop?search=games", [
        ("Indoor Games", "/shop?search=indoor+games"),
        ("Party Games", "/shop?search=party+games"),
        ("Puzzles", "/shop?search=puzzle"),
    ]),
    ("Your Pad", "/shop?search=home", [
        ("Drinking", "/shop?search=drinking"),
        ("Kitchen", "/shop?search=kitchen"),
        ("Party", "/shop?search=party"),
        ("Personal Care", "/shop?search=personal+care"),
    ]),
]


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

    _seed_rockos_menu(env, website)


def _seed_rockos_menu(env, website):
    parameter = env["ir.config_parameter"].sudo()
    seed_key = f"rockos_website_theme.menu_seeded.{website.id}"
    if parameter.get_param(seed_key) == ROCKOS_MENU_VERSION:
        return

    root_menu = website.menu_id.sudo()
    if not root_menu:
        return

    # The initial tree is seeded once. Future changes belong to Odoo's menu editor.
    root_menu.child_id.unlink()
    Menu = env["website.menu"].sudo()
    for sequence, (name, url, children) in enumerate(ROCKOS_MENU_TREE, start=10):
        parent = Menu.create({
            "name": name,
            "url": url,
            "parent_id": root_menu.id,
            "website_id": website.id,
            "sequence": sequence,
        })
        for child_sequence, (child_name, child_url) in enumerate(children, start=10):
            Menu.create({
                "name": child_name,
                "url": child_url,
                "parent_id": parent.id,
                "website_id": website.id,
                "sequence": child_sequence,
            })
    parameter.set_param(seed_key, ROCKOS_MENU_VERSION)


def _setup_rockos_pages(env, website):
    Page = env["website.page"].sudo()
    for name, url, xmlid in ROCKOS_PAGES:
        view = env.ref(xmlid, raise_if_not_found=False)
        if not view:
            continue
        if view.website_id != website:
            view.website_id = website.id
        page = Page.search([
            ("website_id", "=", website.id),
            ("url", "=", url),
        ], limit=1)
        values = {
            "name": name,
            "url": url,
            "view_id": view.id,
            "website_id": website.id,
            "website_published": True,
        }
        if page:
            page.write(values)
        else:
            Page.create(values)


def _setup(env):
    branch = _get_or_create_rockos_branch(env)
    website = _get_or_create_rockos_website(env, branch)
    _scope_views_to_rockos(env, website)
    _configure_rockos_website(env, website)
    _setup_rockos_pages(env, website)


def post_init_hook(env):
    _setup(env)


def post_update_hook(env):
    _setup(env)
