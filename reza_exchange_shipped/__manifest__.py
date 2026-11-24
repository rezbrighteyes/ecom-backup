# -*- coding: utf-8 -*-
{
    "name": "Reza: Exchange or Refund After Delivery",
    "summary": "Exchange or refund an item the customer has sent back, return it to Edbert, and check the refund really went out",
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

The "Refund (shipped)" button does the same for a customer who wants their
money back: return in, credit note at the price paid (shipping only when
ticked), goods back to Edbert, and a Customer Refund row that a daily cron
checks against Stripe or PayPal until the money has really gone back.

Odoo sends a Stripe refund itself only when "Send refunds through Odoo" is on
(Sales > Settings; off by default). Otherwise the refund user (Accounts Dept)
gets a task with the amount, provider and transaction.
""",
    "author": "Reza",
    "category": "Sales/Sales",
    "version": "20.0.1.5.0",
    "license": "OPL-1",
    "depends": ["reza_sale_unable_to_supply", "reza_ecom_intercompany_po", "account_payment", "delivery"],
    "data": [
        "security/old_buttons_group.xml",
        "data/ir_cron_data.xml",
        "views/edbert_return_views.xml",
        "views/customer_refund_views.xml",
        "views/sale_order_views.xml",
        "views/old_buttons_views.xml",
        "wizard/exchange_shipped_views.xml",
        "wizard/refund_shipped_views.xml",
        'security/ir.access.csv',
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
