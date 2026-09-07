# -*- coding: utf-8 -*-
"""Thin client for the Google Places API (New).

Only two calls are used:

* ``places:searchText`` — to resolve a stockist to a place id when we do not have
  one. ``store-codes.csv`` holds CIDs, and Google does not officially convert a CID
  to a place id, so a text search on name + address is the supported route.
* ``places/{id}``      — to read the address, phone and hours.

Field masks are mandatory on this API and they drive billing: asking for fewer
fields costs less. The masks below are the minimum for what the sync writes.

TERMS OF SERVICE, worth knowing before this is pointed at third-party stockists:
Google permits caching ``place_id`` indefinitely, but other Places content for
**30 days**. For locations the group owns that restriction does not apply — those
should move to the Business Profile API once Google approves access. See README.
"""
import logging

import requests

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BASE = "https://places.googleapis.com/v1"
TIMEOUT = 20

DETAIL_MASK = ",".join([
    "id",
    "displayName",
    "formattedAddress",
    "addressComponents",
    "location",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "regularOpeningHours",
    "websiteUri",
    "businessStatus",
])

SEARCH_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
])


def _headers(api_key, field_mask):
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }


def _raise_for(response):
    """Turn an API error into something a user can act on."""
    if response.status_code == 200:
        return
    detail = ""
    try:
        detail = (response.json().get("error") or {}).get("message") or ""
    except ValueError:
        detail = response.text[:200]
    if response.status_code in (401, 403):
        raise UserError(_(
            "Google rejected the request (%s). Check that the Places API is enabled "
            "on the Cloud project and that the key's restrictions allow it.\n\n%s"
        ) % (response.status_code, detail))
    if response.status_code == 429:
        raise UserError(_("Google rate-limited the request. Try again shortly."))
    raise UserError(_("Google Places returned %s.\n\n%s") % (response.status_code, detail))


def search_place(api_key, text_query, region_code="AU"):
    """Return the first match for a free-text query, or None."""
    body = {"textQuery": text_query, "maxResultCount": 5}
    if region_code:
        body["regionCode"] = region_code
    response = requests.post(
        "%s/places:searchText" % BASE,
        headers=_headers(api_key, SEARCH_MASK),
        json=body,
        timeout=TIMEOUT,
    )
    _raise_for(response)
    places = response.json().get("places") or []
    return places[0] if places else None


def get_place(api_key, place_id):
    """Full detail for one place id."""
    response = requests.get(
        "%s/places/%s" % (BASE, place_id),
        headers=_headers(api_key, DETAIL_MASK),
        timeout=TIMEOUT,
    )
    _raise_for(response)
    return response.json()


# ----------------------------------------------------------------------
# Parsing — deliberately pure functions so they can be tested without network
# ----------------------------------------------------------------------
def parse_address_components(payload):
    """Google addressComponents -> the fields this model stores.

    Returns a dict with street, street2, city, state_code, zip, country_code.
    Missing pieces are returned as empty strings rather than omitted, so callers
    can diff against current values without KeyErrors.
    """
    by_type = {}
    for component in payload.get("addressComponents") or []:
        for type_name in component.get("types") or []:
            by_type.setdefault(type_name, component)

    def long(type_name):
        return (by_type.get(type_name) or {}).get("longText") or ""

    def short(type_name):
        return (by_type.get(type_name) or {}).get("shortText") or ""

    street_number = long("street_number")
    route = long("route")
    subpremise = long("subpremise")

    street = " ".join(p for p in [street_number, route] if p).strip()
    # Australian shopping-centre addresses put the shop number in subpremise.
    if subpremise and street:
        street = "%s/%s" % (subpremise, street)
    elif subpremise:
        street = subpremise

    # Google's "locality" is the suburb in AU. Fall back through the postal
    # town and the smallest admin area when locality is absent, which happens
    # for addresses inside large centres.
    city = long("locality") or long("postal_town") or long("administrative_area_level_2")

    return {
        "street": street,
        "street2": long("neighborhood") if street else "",
        "city": city,
        "state_code": short("administrative_area_level_1"),
        "zip": long("postal_code"),
        "country_code": short("country"),
    }


def parse_opening_hours(payload):
    """regularOpeningHours -> the newline text this model stores, or ''."""
    hours = payload.get("regularOpeningHours") or {}
    descriptions = hours.get("weekdayDescriptions") or []
    return "\n".join(d.strip() for d in descriptions if d and d.strip())


def parse_location(payload):
    """location -> (latitude, longitude), or (None, None)."""
    location = payload.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")
    if lat is None or lng is None:
        return None, None
    return float(lat), float(lng)


def parse_phone(payload):
    """Prefer the national format — that is what a customer dials locally."""
    return (payload.get("nationalPhoneNumber")
            or payload.get("internationalPhoneNumber")
            or "")
