# -*- coding: utf-8 -*-
{
    "name": "Reza: Ecom Intercompany Purchase",
    "summary": "Raise a purchase order on Edbert when an ecom sale confirms",
    "description": """
Ecom holds no stock. Edbert owns it. When an ecom sale order confirms, this
raises the matching purchase order on Edbert and confirms it, which makes
`d3_external_api` push the counterpart sale order into the wholesale database.

The purchase price is what Edbert charges the brand: the price on the pricelist
of the brand's customer record in wholesale, read live. That pricelist must be
the one in the system parameter reza_ecom_intercompany_po.edbert_pricelist_id,
or the order fails with a note. ecom's own standard_price is never used.

It never blocks a customer's order. A failure is logged and recorded on the
sale order for somebody to pick up.
""",
    "author": "Reza",
    "website": "https://d-3.com.au",
    "category": "Inventory/Purchase",
    "version": "18.0.1.5.0",
    "license": "OPL-1",
    "depends": ["sale", "sale_stock", "purchase", "purchase_stock", "d3_external_api"],
    "data": [
        "data/ir_cron_data.xml",
        "data/ir_config_parameter_data.xml",
        "views/sale_order_views.xml",
        "views/purchase_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
