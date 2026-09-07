# -*- coding: utf-8 -*-
"""Diff-then-confirm sync from Google Places.

Nothing is written to a stockist by fetching. The wizard shows what Google holds
beside what we hold, and the user ticks which groups to apply. That is deliberate:
the eight address conflicts found on 26 Aug are not all formatting — Rockhampton's
Google address names a different suburb than the website does — so a silent
overwrite would change how stores are described with nobody reading it.
"""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models import google_places

_logger = logging.getLogger(__name__)

PARAM_KEY = "website_stockist.google_places_api_key"


class StockistGoogleSync(models.TransientModel):
    _name = "website.stockist.google.sync"
    _description = "Fetch stockist details from Google Places"

    stockist_id = fields.Many2one("website.stockist", required=True, readonly=True)
    place_id = fields.Char(string="Google Place ID", readonly=True)
    matched_name = fields.Char(readonly=True)
    business_status = fields.Char(readonly=True)
    diff_html = fields.Html(readonly=True, sanitize=False)

    apply_address = fields.Boolean(string="Apply address", default=True)
    apply_phone = fields.Boolean(string="Apply phone", default=True)
    apply_hours = fields.Boolean(string="Apply opening hours", default=True)
    apply_coordinates = fields.Boolean(string="Apply coordinates", default=True)

    # Staged values, filled by the fetch, applied on confirm.
    new_street = fields.Char(readonly=True)
    new_street2 = fields.Char(readonly=True)
    new_city = fields.Char(readonly=True)
    new_state_id = fields.Many2one("res.country.state", readonly=True)
    new_zip = fields.Char(readonly=True)
    new_country_id = fields.Many2one("res.country", readonly=True)
    new_phone = fields.Char(readonly=True)
    new_hours = fields.Text(readonly=True)
    new_latitude = fields.Float(digits=(10, 7), readonly=True)
    new_longitude = fields.Float(digits=(10, 7), readonly=True)

    # ------------------------------------------------------------------
    @api.model
    def _api_key(self):
        key = self.env["ir.config_parameter"].sudo().get_param(PARAM_KEY)
        if not key:
            raise UserError(_(
                "No Google Places API key is configured.\n\n"
                "Set it in Settings > Technical > System Parameters, key:\n  %s\n\n"
                "The key needs the Places API (New) enabled on the Cloud project."
            ) % PARAM_KEY)
        return key

    # ------------------------------------------------------------------
    @api.model
    def build_for_stockist(self, stockist):
        """Call Google, stage the values, return a wizard record. Writes nothing."""
        key = self._api_key()
        place_id = stockist.google_place_id

        if not place_id:
            query = " ".join(p for p in [stockist.name, stockist.full_address] if p)
            if not query.strip():
                raise UserError(_("Give the stockist a name or an address before fetching."))
            match = google_places.search_place(key, query)
            if not match:
                raise UserError(_(
                    "Google found no place matching:\n\n  %s\n\n"
                    "Refine the name or address, or paste a Place ID directly."
                ) % query)
            place_id = match.get("id")

        payload = google_places.get_place(key, place_id)
        parsed = google_places.parse_address_components(payload)
        lat, lng = google_places.parse_location(payload)

        state = self.env["res.country.state"]
        country = self.env["res.country"]
        if parsed["country_code"]:
            country = country.search([("code", "=", parsed["country_code"])], limit=1)
        if parsed["state_code"] and country:
            state = state.search([
                ("country_id", "=", country.id),
                ("code", "=", parsed["state_code"]),
            ], limit=1)

        values = {
            "stockist_id": stockist.id,
            "place_id": place_id,
            "matched_name": (payload.get("displayName") or {}).get("text") or "",
            "business_status": payload.get("businessStatus") or "",
            "new_street": parsed["street"],
            "new_street2": parsed["street2"],
            "new_city": parsed["city"],
            "new_state_id": state.id or False,
            "new_zip": parsed["zip"],
            "new_country_id": country.id or False,
            "new_phone": google_places.parse_phone(payload),
            "new_hours": google_places.parse_opening_hours(payload),
            "new_latitude": lat or 0.0,
            "new_longitude": lng or 0.0,
        }
        wizard = self.create(values)
        wizard.diff_html = wizard._build_diff_html()
        return wizard

    # ------------------------------------------------------------------
    def _diff_rows(self):
        self.ensure_one()
        s = self.stockist_id
        return [
            ("Street", s.street, self.new_street),
            ("Street 2", s.street2, self.new_street2),
            ("City / suburb", s.city, self.new_city),
            ("State", s.state_id.code or s.state_id.name or "",
             self.new_state_id.code or self.new_state_id.name or ""),
            ("Postcode", s.zip, self.new_zip),
            ("Country", s.country_id.name or "", self.new_country_id.name or ""),
            ("Phone", s.phone, self.new_phone),
            ("Opening hours", s.opening_hours, self.new_hours),
            ("Latitude", s.partner_latitude or "", self.new_latitude or ""),
            ("Longitude", s.partner_longitude or "", self.new_longitude or ""),
        ]

    def _build_diff_html(self):
        self.ensure_one()
        from markupsafe import Markup, escape

        rows = []
        for label, current, incoming in self._diff_rows():
            current_text = "" if current in (None, False) else str(current)
            incoming_text = "" if incoming in (None, False) else str(incoming)
            changed = current_text.strip() != incoming_text.strip()
            if not incoming_text.strip():
                # Google has nothing to offer for this field; never blank ours.
                style, note = "color:#888;", " (Google has no value — left alone)"
            elif changed:
                style, note = "background:#fff3cd;", ""
            else:
                style, note = "", " (same)"
            rows.append(Markup(
                "<tr style='%s'><td><b>%s</b></td>"
                "<td style='white-space:pre-wrap'>%s</td>"
                "<td style='white-space:pre-wrap'>%s%s</td></tr>"
            ) % (Markup(style), escape(label), escape(current_text),
                 escape(incoming_text), Markup(note)))

        return Markup(
            "<table class='table table-sm'>"
            "<thead><tr><th>Field</th><th>Currently on the site</th>"
            "<th>Google Business Profile</th></tr></thead><tbody>%s</tbody></table>"
        ) % Markup("").join(rows)

    # ------------------------------------------------------------------
    def action_apply(self):
        self.ensure_one()
        stockist = self.stockist_id
        vals = {"google_place_id": self.place_id,
                "google_sync_date": fields.Datetime.now()}

        def keep(new, old):
            """Never blank an existing value because Google has nothing."""
            return new if (new not in (None, False, "")) else old

        if self.apply_address:
            vals.update({
                "street": keep(self.new_street, stockist.street),
                "street2": keep(self.new_street2, stockist.street2),
                "city": keep(self.new_city, stockist.city),
                "zip": keep(self.new_zip, stockist.zip),
            })
            if self.new_state_id:
                vals["state_id"] = self.new_state_id.id
            if self.new_country_id:
                vals["country_id"] = self.new_country_id.id
        if self.apply_phone:
            vals["phone"] = keep(self.new_phone, stockist.phone)
        if self.apply_hours:
            vals["opening_hours"] = keep(self.new_hours, stockist.opening_hours)
        if self.apply_coordinates and self.new_latitude and self.new_longitude:
            vals["partner_latitude"] = self.new_latitude
            vals["partner_longitude"] = self.new_longitude

        stockist.write(vals)
        stockist.message_post(body=_(
            "Synced from Google Places (place id %s). Applied: %s."
        ) % (self.place_id, ", ".join(filter(None, [
            "address" if self.apply_address else None,
            "phone" if self.apply_phone else None,
            "hours" if self.apply_hours else None,
            "coordinates" if self.apply_coordinates else None,
        ])) or "nothing"))
        return {"type": "ir.actions.act_window_close"}
