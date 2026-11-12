# -*- coding: utf-8 -*-
{
    "name": "Reza: Exchange After Delivery",
    "summary": "Exchange an item the customer has sent back, and return it to Edbert",
    "description": """
The "Exchange (shipped)" button on a delivered sale order handles a customer
who sends an item back and wants a different one (or the same one again).

One click, after the item is back in the shed:

* receives the item back from the customer (a return of the delivery);
* credits the customer for it;
* puts the replacement on a NEW sale order linked to the first one, so the
  Edbert bridge buys it from Edbert after it ships, exactly like any order;
* invoices the replacement and matches the credit against it, so the order
  chatter says what the customer owes or what to refund;
* queues the returned item to go back to Edbert on paper: the ecom receipt is
  returned, the Edbert delivery is returned, and a vendor credit and an Edbert
  credit note are raised and posted only when the two agree.

It never moves money. A refund to the customer is still done in PayPal or
Stripe, by a person.
""",
    "author": "Reza",
    "category": "Sales/Sales",
    "version": "18.0.1.1.0",
    "license": "OPL-1",
    "depends": ["reza_sale_unable_to_supply", "reza_ecom_intercompany_po"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/edbert_return_views.xml",
        "views/sale_order_views.xml",
        "wizard/exchange_shipped_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
