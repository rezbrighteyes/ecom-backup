# -*- coding: utf-8 -*-
"""Let the shop sell what Edbert holds.

Ecom holds almost no stock of its own; the intercompany bridge buys from Edbert
after each order ships. So for a product with "Continue selling when
out-of-stock" switched OFF, website_sale_stock would call almost everything
sold out. This file adds Edbert's figure to the quantity the shop may sell:

    sellable = max(own free, 0)
             + max(Edbert free - buffer, 0)      only when matched and fresh
             - ecom demand not yet delivered and not reserved
    (never below 0)

Why each term:

* Own free stock is floored at 0. A negative position on ecom is an order
  that shipped before the bridge's purchase was received; Edbert has already
  been asked for those units, so they are in Edbert's figure at the next sync.
  Subtracting them again would count them twice.
* The buffer (default 1) covers the hour between syncs, during which Edbert
  can sell the last units to a wholesale customer.
* The Edbert figure counts only when the match is "ok". Any other state means
  the figure belongs to no proven product, so it is not used.
* The Edbert figure counts only when the last full sync is younger than the
  stale limit (default 3 hours). If the sync stops, the shop stops selling on
  Edbert's word instead of selling on an old number.
* Undelivered ecom demand is subtracted because the bridge buys from Edbert
  only AFTER dispatch: an ecom order waiting to ship has not touched Edbert's
  figure yet. Demand is counted across every ecom company, because every site
  draws on the same Edbert warehouse. Reserved quantity is left out: that part
  is held against ecom's own stock, which own free already excludes.

The result is then banded (see _band): exact under 5, otherwise 5, 10 or 20,
rounded down, so the shop never shows Edbert's real position.

Products with "Continue selling" ON are not stock-checked at the cart, but
the product page still asks for this figure (combination info), so they get
the banded number there too. Products without a proved match get exactly the
core figure.

Every read here is sudo(): the Edbert fields are limited to base.group_user
(see product_product.py), and a shop visitor is base.group_public. Without
sudo() an anonymous product page would answer 403.
"""

from datetime import timedelta

from odoo import fields, models

PARAM_BUFFER = "reza_ecom_edbert_stock.sell_buffer_qty"
PARAM_STALE_HOURS = "reza_ecom_edbert_stock.sell_stale_hours"
DEFAULT_BUFFER = 1
DEFAULT_STALE_HOURS = 3
# Edbert's position is not to be read off the shop. The figure goes to every
# visitor (it is in /website_sale/get_combination_info whether or not the page
# prints it), so below EXACT_BELOW it is exact ("Only 3 left") and above it is
# rounded DOWN to a band. Rounding down never sells what is not there; it only
# limits one order to the band.
LOOKBACK_DAYS = 14
EXACT_BELOW = 5
BANDS = (20, 10, 5)


def _band(qty):
    if qty < EXACT_BELOW:
        return qty
    for band in BANDS:
        if qty >= band:
            return float(band)
    return qty


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _reza_edbert_sellable_qty(self, own_free):
        """Return the quantity the shop may sell, given ecom's own free qty."""
        self.ensure_one()
        product = self.sudo()
        if product.reza_edbert_stock_state != "ok":
            return own_free
        sync = self.env["reza.edbert.stock.sync"].sudo()
        stale_hours = sync._int_param(PARAM_STALE_HOURS, DEFAULT_STALE_HOURS)
        last = sync._last_sync()
        if not last or last < fields.Datetime.now() - timedelta(hours=stale_hours):
            return own_free
        buffer = sync._int_param(PARAM_BUFFER, DEFAULT_BUFFER)
        edbert = max(product.reza_edbert_free_qty - buffer, 0.0)
        sellable = (
            max(own_free, 0.0)
            + edbert
            - product._reza_unreserved_demand()
            - product._reza_shipped_not_at_edbert(last)
        )
        return _band(max(sellable, 0.0))

    def _reza_shipped_not_at_edbert(self, last_sync):
        """Shipped ecom quantity that Edbert's last figure does not yet show.

        A delivery leaves the open demand above the moment it is done, but the
        bridge (reza_ecom_intercompany_po) orders from Edbert only afterwards,
        and Edbert's figure drops only at the next sync after that. In between,
        the same units would count as available twice. They are still counted
        here while the order's Edbert purchase is not raised (pending, failed)
        or was confirmed after the last sync. Looks back LOOKBACK_DAYS only, so
        the read stays small; a failure older than that is a bridge problem the
        bridge itself reports.
        """
        self.ensure_one()
        since = fields.Datetime.now() - timedelta(days=LOOKBACK_DAYS)
        base = [
            ("product_id", "=", self.id),
            ("state", "=", "done"),
            ("date", ">=", since),
            ("location_id.usage", "=", "internal"),
            ("location_dest_id.usage", "=", "customer"),
        ]
        order = "sale_line_id.order_id."
        domain = base + [
            "|",
            (order + "reza_edbert_status", "in", ("pending", "failed")),
            "&",
            (order + "reza_edbert_status", "in", ("raised", "partial")),
            (order + "reza_edbert_purchase_id.date_approve", ">", last_sync),
        ]
        groups = self.env["stock.move"]._read_group(domain, [], ["quantity:sum"])
        return (groups[0][0] if groups else 0.0) or 0.0

    def _reza_unreserved_demand(self):
        """Undelivered, unreserved quantity on open ecom customer deliveries.

        Called on the sudo() product from _reza_edbert_sellable_qty, so the
        stock.move read runs as superuser: a shop visitor has no stock.move
        access at all.
        """
        self.ensure_one()
        groups = self.env["stock.move"]._read_group(
            [
                ("product_id", "=", self.id),
                ("state", "not in", ("draft", "done", "cancel")),
                ("location_id.usage", "=", "internal"),
                ("location_dest_id.usage", "=", "customer"),
            ],
            [],
            ["product_uom_qty:sum", "quantity:sum"],
        )
        demand, reserved = groups[0] if groups else (0.0, 0.0)
        return max((demand or 0.0) - (reserved or 0.0), 0.0)


class Website(models.Model):
    _inherit = "website"

    def _get_product_available_qty(self, product, **kwargs):
        own = super()._get_product_available_qty(product, **kwargs)
        return product._reza_edbert_sellable_qty(own)


# No sale.order override on Odoo 20: the cart's free quantity is
# `sale.order._get_free_qty` -> `website._get_product_available_qty`, which the
# Website override above already adjusts. Odoo 18 read the cart quantity
# without the website method, so it needed its own `_get_cart_and_free_qty`
# override; keeping it here would apply the Edbert figure twice.
