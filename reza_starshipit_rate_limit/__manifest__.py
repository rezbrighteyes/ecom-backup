# -*- coding: utf-8 -*-
{
    "name": "Reza Starshipit Rate Limit",
    "summary": "Wait and retry when Starshipit answers 429, instead of failing the label",
    "description": """
Odoo's Starshipit connector (Enterprise `delivery_starshipit`) sends four or
five calls per label back to back -- look the order up, import it, print the
shipment, read it back, manifest it -- with no pause and no retry. Starshipit
refuses the third or so call inside one second:

    429 { "statusCode": 429, "message": "Rate limit is exceeded. Try again in 1 seconds." }

Odoo then raises "Starshipit API rate exceeded. Please try again later." and
rolls the picking back. But the label already exists in Starshipit, and
validating again prints a NEW label with a new tracking number. Measured on
production 2026-10-06: 23 of ~117 calls refused, 36 label requests for 14
orders, RKS/OUT/00011 holding three labels.

WHAT THIS MODULE DOES

It wraps `requests.Session.send` -- the one method every `requests` call goes
through -- and only for `api.starshipit.com`:

* spaces calls at least MIN_INTERVAL apart within the worker process, so a
  label's own burst no longer trips the limit;
* on a 429, waits for the time Starshipit names (or Retry-After, or 1s) and
  sends the same request again, up to MAX_RETRIES times.

Retrying is safe for POSTs: a 429 is refused at the gate, before Starshipit
processes the request, so no label is created by the refused call.

Every other host is passed straight through, untouched. The Enterprise source
is not available to this repo, so the patch sits below it at the `requests`
layer rather than overriding its methods.

The patch is applied when the module is imported. Uninstalling it takes effect
at the next server restart.
    """,
    "author": "Reza",
    "category": "Inventory/Delivery",
    "version": "18.0.1.0.0",
    "license": "OPL-1",
    "depends": ["delivery"],
    "data": [],
    "installable": True,
    "application": False,
}
