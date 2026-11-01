{
    "name": "Reza Login Geolock",
    "summary": "Refuse staff sign-ins to Odoo from outside Australia",
    "description": """
Reza Login Geolock
==================

Geolocks STAFF sign-ins only. An internal user (``share = False``) who signs
in to Odoo from an IP address outside the allowed countries is refused, and
the attempt is recorded. Portal users, website visitors and shop customers
are never checked, so the websites and the B2B store portal are unaffected.

Three sign-in paths are covered: the web login form, XML-RPC / JSON-RPC calls
(password or API key, checked on every call, not only the first), and
bearer-token (API key) routes (``auth='bearer'``, e.g. ``/json/1``).

Settings > General Settings > Staff Sign-in Geolock:

* Mode: Off, Report only (record, never block) or Block. Installs as
  Report only.
* Allowed countries: ISO codes, comma separated. Default ``AU``.

Open sessions are checked too: a staff session seen from a disallowed
country is ended (Block mode) or recorded (Report only).

Only members of "Sign-in Geolock Manager" see the settings, the log and the
exemption box. The group is given to the Administrator user on install and
to nobody else.

The Administrator login is exempt from install.

A user can be exempted with "Allow sign-in from any country" on the
Account Security tab of the user form (travel, or an integration that runs from
overseas, such as Claude's Odoo connector on the Administrator login).

Private and loopback addresses (Odoo.sh's own scheduled jobs) and addresses
the GeoIP database cannot place are always allowed. Every refusal or would-be
refusal is listed under Settings > Users & Companies > Sign-in Geolock.
    """,
    "author": "Reza",
        "category": "Administration",
    "version": "18.0.1.0.0",
    "depends": ["base", "base_setup"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/admin_exempt.xml",
        "views/geolock_event_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
