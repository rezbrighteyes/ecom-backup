# -*- coding: utf-8 -*-
{
    "name": "Reza: Cannot Supply & Exchange",
    "summary": "Buttons to take an item off a confirmed order, or swap it, and fix the invoice",
    "description": """
When an item on a confirmed order cannot be supplied, staff used to edit the
order line, reverse the invoice and rebuild a credit note by hand. That took
many clicks and invited mistakes (a full reversal, edits to a paid invoice).

The "Cannot Supply" button on the sale order does it in one step:

* lowers the ordered quantity, which cancels the matching stock move;
* if that quantity was already invoiced, raises a credit note for exactly the
  removed quantity, linked to the invoice and to the order line, and posts it;
  Odoo then matches it against the invoice;
* writes on the order how much to refund and through which payment provider.

The "Exchange" button swaps an item that has not shipped for another one.
If the price differs by less than $1 the customer keeps the price paid;
otherwise the order chatter says what is owed or what to refund.

It never moves money. The refund to the customer is still done in PayPal or
Stripe, by a person.
""",
    "author": "Reza",
    "category": "Sales/Sales",
    "version": "18.0.1.1.0",
    "license": "OPL-1",
    "depends": ["sale_stock", "account"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/unable_to_supply_views.xml",
        "wizard/exchange_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
