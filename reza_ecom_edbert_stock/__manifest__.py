# -*- coding: utf-8 -*-
{
    "name": "Reza Ecom Edbert Stock",
    "summary": "Show Edbert's free stock on ecom products, and let the shop sell it",
    "description": """
Ecom holds almost no stock of its own. Edbert holds it, and the intercompany
bridge (`reza_ecom_intercompany_po`) buys it order by order. So an ecom product
reads zero on hand while Edbert may hold thousands.

This module puts Edbert's figure on the ecom product. The sync writes no
quants, posts no journal entry, touches no valuation and does not change
`allow_out_of_stock_order`.

SELLING ON EDBERT'S STOCK (18.0.1.1.0)

For a product with "Continue selling when out-of-stock" OFF, the shop may sell
its own free stock plus Edbert's free stock less a buffer of 1, less ecom
orders not yet shipped, shown exact under 5 and otherwise rounded down to
5, 10 or 20 so Edbert's real position never reaches the shop. Edbert's part counts only when the match is proved and
the last sync is under 3 hours old. See models/website_stock.py. Settings:
`reza_ecom_edbert_stock.sell_buffer_qty`, `reza_ecom_edbert_stock.sell_stale_hours`.
Products with "Continue selling" ON are not affected.

    Measured on production 2026-09-07: Edbert's WH/Stock held 2,854 products
    and 1,427,419 free units. Of ecom's 1,688 published storable templates,
    1,625 matched an Edbert product and 902 of those had stock.

WHY THE MATCH IS CHECKED, AND HOW

`product.product.external_api_id` holds the wholesale product id, and it rots.
Measured on production 2026-09-07, of 15,681 ecom products carrying one, 5,374
point at a wholesale id that no longer exists.

So the figure is only shown once the two records are proved to be the same
product: the wholesale product must carry the ecom product's reference, either
as its own internal reference or as its barcode. Where it does not, no number
is shown and the product says why.

The barcode half of that check is not optional. The two catalogues label the
same product differently -- ecom knows Rocko's Tread Thongs size 08 as
`9340457002310` and wholesale knows it as `4178Treads08`, with the EAN in the
barcode. 31 products are in that state on production and every one of them is
a CORRECT mapping. Checking the reference alone would have withheld all 31,
15 of them on published products.

`reza_generic_barcode` is deliberately not used. It is a model-level number
shared by every size of a product, so it would let size 14 verify against size
08's mapping. `barcode` carries a uniqueness constraint; that one can.

WHY THE STATE FIELD EXISTS

A blank number would mean two different things: "Edbert holds none" and "we
could not match this product". Those need different actions from different
people, so each product carries a state that says which it is.

REFUSALS

The run stops and writes nothing at all when the wholesale location is not an
internal Edbert location, when the quant read comes back shorter than the
configured floor, or when every row reads zero. A truncated or misdirected
read cannot blank the catalogue.
    """,
    "author": "Reza",
    "category": "Inventory/Inventory",
    "version": "20.0.1.1.0",
    "license": "LGPL-3",
    "depends": [
        "product",
        "stock",
        "d3_external_api",
        "website_sale_stock",
        # Also overrides website._get_product_available_qty without calling
        # super() in one branch; depending on it keeps this module ABOVE it.
        "d3_website_product_extended",
        # reza_edbert_status / reza_edbert_purchase_id on sale.order: which
        # shipped units Edbert's figure does not show yet.
        "reza_ecom_intercompany_po",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "views/product_views.xml",
    ],
    "installable": True,
    "application": False,
}
