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
Security tab of the user form (travel, or an integration that runs from
overseas, such as Claude's Odoo connector on the Administrator login).

Specific addresses can be allowed from outside the allowed countries under
Settings > Users & Companies > Sign-in Geolock IP Addresses: one IPv4 or IPv6
address or CIDR range per line, optionally only for named users (a staff
member's fixed line overseas, without exempting them from every country).
Removing an address ends the open sessions using it on their next request.

IP lock: "Sign in only from allowed IP addresses" on the user form limits a
user to the active allow-list entries that name them, in any country and in
any geolock mode, so a VPN exiting in Australia does not get through. Every
other sign-in with the right password is refused, listed as an IP lock breach
and emailed to the geolock managers (or to the addresses in the system
parameter reza_login_geolock.alert_to).

res.users.reza_geolock_end_sessions() ends every open session of the IP-locked
users it is called on, for administrators only. The office server calls it
right after its random Microsoft 365 sign-out, so the person is signed out of
Odoo at the same moment.

Private and loopback addresses (Odoo.sh's own scheduled jobs) and addresses
the GeoIP database cannot place are always allowed. Every refusal or would-be
refusal is listed under Settings > Users & Companies > Sign-in Geolock.
    """,
    "author": "Reza",
        "category": "Administration",
    "version": "20.0.1.3.0",
    "depends": ["base", "base_setup", "rpc"],
    "data": [
        "security/security.xml",
        "data/admin_exempt.xml",
        "views/geolock_event_views.xml",
        "views/geolock_ip_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
        'security/ir.access.csv',
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
