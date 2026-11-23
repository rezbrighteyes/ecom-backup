import logging

from markupsafe import Markup, escape

from odoo import api, models

_logger = logging.getLogger(__name__)


class RezLoginGeolockEvent(models.Model):
    _inherit = "reza.login.geolock.event"

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        for event in events:
            # Geolock writes its event on its own cursor and swallows any
            # error, so a failure here would lose the geolock record itself.
            # Run in a savepoint and never let it raise.
            try:
                with self.env.cr.savepoint():
                    event._reza_to_activity_log()
            except Exception:  # noqa: BLE001
                _logger.exception("Sessions geolock: could not add event %s to the activity log", event.id)
        return events

    def _reza_to_activity_log(self):
        self.ensure_one()
        action = dict(self._fields["action"]._description_selection(self.env)).get(self.action, self.action)
        channel = dict(self._fields["channel"]._description_selection(self.env)).get(self.channel, self.channel)
        value = Markup("<b>%s</b> from <b>%s</b> (%s) via %s.<br/>") % (
            escape(action), escape(self.country or "unknown country"),
            escape(self.ip or "no IP"), escape(channel))
        self.env["activity.log"].sudo().create({
            "name": "%s: %s %s" % (self.login, action, self.country or ""),
            "model": self._name,
            "res_id": str(self.id),
            "action": "geolock",
            "user_id": self.user_id.id or False,
            "value": value,
            "view": "n/a",
        })
