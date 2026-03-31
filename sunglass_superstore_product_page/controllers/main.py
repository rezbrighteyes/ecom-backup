from datetime import datetime, timedelta

from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request, route

SUNGLASS_SUPERSTORE_WEBSITE_ID = 5


def _estimate_delivery(business_days=3):
    """Return estimated delivery N business days from today as 'MONDAY 06 APRIL'."""
    d = datetime.now()
    added = 0
    while added < business_days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.strftime('%A %d %B').upper()


class SunglassSuperstoreWebsiteSale(WebsiteSale):

    @route()
    def product(self, product, category='', search='', **kwargs):
        response = super().product(
            product, category=category, search=search, **kwargs
        )
        if (
            request.website.id == SUNGLASS_SUPERSTORE_WEBSITE_ID
            and isinstance(response, dict)
        ):
            response['estimated_delivery_date'] = _estimate_delivery(3)
        return response
