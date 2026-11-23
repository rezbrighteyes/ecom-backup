{
    "name": "Sessions: Sign-in Geolock",
    "summary": "Show geolock refusals and allowed IPs inside the Sessions app",
    "description": """
Links advanced_session_management and reza_login_geolock without changing
either. Adds the geolock refusal list and the allowed IP list under the
Sessions app, writes every geolock refusal into the Activity Log next to
that user's sessions, and shows the country on the Sessions list.
Installs itself when both modules are installed.
    """,
    "author": "Reza",
    "category": "Administration",
    "version": "18.0.1.0.0",
    "depends": ["advanced_session_management", "reza_login_geolock"],
    "data": [
        "views/menus.xml",
        "views/res_device_views.xml",
    ],
    "auto_install": True,
    "installable": True,
    "license": "LGPL-3",
}
