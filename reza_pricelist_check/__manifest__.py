# -*- coding: utf-8 -*-
{
    "name": "Price List Check",
    "summary": "See every product a price list charges, conflicting rules, and every rule across all lists",
    "description": """
Ported from the wholesale database's reza_pricelist_check (19.0.1.8.0),
without the brand caps, allowed brands and promotions that ecom does not have.

1. CHECK PRICES (button on every price list). Lists every product that can
   be sold, with its Sale Price, the price this list charges for one unit
   today, the % off, and the rule that produced it. Each row is marked:
   Discounted / Not allowed a discount / Not discounted / Above sale /
   Zero price / Below cost. A product that two or more rules on the list
   match is flagged as a Conflict (different prices) or an Overlap (same
   price), with the rules it beat and why the winner won.

   Prices come from the list's own engine (product.pricelist
   _get_product_price_rule), so chained lists, rounding and margins behave
   exactly as on an order. While a check runs, the rules are fetched once
   per list for the whole product set rather than once per product.

2. PRICE RULES (Sales > Products > Price Rules, and a button on each list).
   Every rule on every list in one place, grouped by list, then by what it
   applies to, then by category. Expired rules are hidden by default.
   Shows what each product/variant rule works out to and whether it is the
   rule actually in use.

3. PRICE LISTS (button on every product). The reverse of Check Prices:
   one row per price list showing what it charges for this product and the
   rule that decides it.

Read only, except the Exclude from Discount / Allow Discount Again buttons.
""",
    "version": "20.0.1.0.0",
    "category": "Sales",
    "author": "Reza",
    "license": "LGPL-3",
    "depends": ["product", "sale", "website_sale"],
    "data": [
        "views/pricelist_check_views.xml",
        "views/pricelist_item_views.xml",
        "views/pricelist_views.xml",
        "views/res_partner_views.xml",
        "views/product_views.xml",
        'security/ir.access.csv',
    ],
    "installable": True,
    "application": False,
}
