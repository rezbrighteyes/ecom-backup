# -*- coding: utf-8 -*-
{
    "name": "Website Stockists",
    "summary": "Stockist / dealer directory with per-website assignment and crawlable, "
               "schema-marked public pages.",
    "description": """
Website Stockists
=================

Maintain a directory of stockists (retailers who carry your brand) and publish it
on one, several, or all of the websites running on this instance.

Key points
----------
* ``website_ids`` is a **many2many**, matching the convention already used on
  ``product.template`` in this database: leaving it empty means *all websites*,
  and setting it restricts the stockist to the chosen ones.
* Public pages are **server-rendered**, so every stockist link is a real crawlable
  ``<a href>`` rather than a JavaScript-built list. That is the entire SEO point of
  a stockist directory.
* Each stockist page emits ``Store`` JSON-LD; the index emits ``ItemList``.
* Per-record SEO metadata via ``website.seo.metadata``.
* Stockists appear in the XML sitemap of every website they are assigned to.
""",
    "version": "18.0.8.0.0",
    "category": "Website",
    "author": "BrightEyes Group",
    "license": "OPL-1",
    "depends": [
        "website",
        "mail",
        # stockist_tag_ids is a many2many to product.tag, which the product module
        # owns. website does not pull product in, so without this the registry
        # build depends on load order rather than on anything declared.
        "product",
        "base_geolocalize",
        # The "become a stockist" form turns a submission into a helpdesk
        # ticket, so helpdesk.ticket and helpdesk.team must exist before this
        # module's controller is loaded.
        "helpdesk",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/stockist_security.xml",
        "wizard/stockist_google_sync_views.xml",
        "views/product_tag_views.xml",
        "views/stockist_views.xml",
        "views/stockist_templates.xml",
        "views/stockist_apply_templates.xml",
        "views/res_config_settings_views.xml",
        "views/canonical_override.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_stockist/static/src/scss/stockist.scss",
        ],
    },
    "external_dependencies": {"python": ["requests"]},
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
