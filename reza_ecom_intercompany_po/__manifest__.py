# -*- coding: utf-8 -*-
{
    "name": "Reza: Ecom Intercompany Purchase",
    "summary": "Raise a purchase order on Edbert when an ecom sale confirms",
    "description": """
Ecom holds no stock. Edbert owns it. When an ecom sale order confirms, this
raises the matching purchase order on Edbert and confirms it, which makes
`d3_external_api` push the counterpart sale order into the wholesale database.

The purchase price is EDBERT'S cost, read live from wholesale -- ecom's own
standard_price is a different figure entirely and must not be used.

It never blocks a customer's order. A failure is logged and recorded on the
sale order for somebody to pick up.
""",
    "author": "Reza",
    "website": "https://d-3.com.au",
    "category": "Inventory/Purchase",
    "version": "18.0.1.4.0",
    "license": "OPL-1",
    "depends": ["sale", "sale_stock", "purchase", "purchase_stock", "d3_external_api"],
    "data": [
        "data/ir_cron_data.xml",
        "views/sale_order_views.xml",
        "views/purchase_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
