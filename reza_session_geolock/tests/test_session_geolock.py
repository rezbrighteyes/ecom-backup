from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestSessionGeolock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create({
            "name": "SG Staff", "login": "sg_staff@example.com",
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
        })
        cls.Event = cls.env["reza.login.geolock.event"].sudo()
        cls.Log = cls.env["activity.log"].sudo()

    def _event(self, **kw):
        vals = {"user_id": self.user.id, "login": self.user.login, "ip": "203.0.113.9",
                "country": "RO", "channel": "web", "action": "blocked"}
        vals.update(kw)
        return self.Event.create(vals)

    def _log_of(self, event):
        return self.Log.search([("model", "=", event._name), ("res_id", "=", str(event.id))])

    def test_refusal_lands_in_activity_log(self):
        event = self._event()
        log = self._log_of(event)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.action, "geolock")
        self.assertEqual(log.user_id, self.user)
        self.assertIn("RO", log.value)
        self.assertIn("203.0.113.9", log.value)

    @mute_logger("odoo.addons.reza_session_geolock.models.geolock_event")
    def test_log_failure_never_loses_the_geolock_event(self):
        with patch.object(type(self.Event), "_reza_to_activity_log", side_effect=RuntimeError("boom")):
            event = self._event(ip="203.0.113.10")
        self.assertTrue(event.exists())
        self.assertFalse(self._log_of(event))

    def test_menus_sit_under_sessions(self):
        root = self.env.ref("advanced_session_management.menu_main_login_log_ah")
        for xmlid in ("reza_session_geolock.menu_session_geolock_event",
                      "reza_session_geolock.menu_session_geolock_ip"):
            self.assertEqual(self.env.ref(xmlid).parent_id, root)

    def test_sessions_list_shows_country(self):
        # Odoo 20: the Sessions menu opens res.session; res.device is kept too.
        for model in ("res.session", "res.device"):
            arch = self.env[model].get_views([(False, "list")])["views"]["list"]["arch"]
            self.assertRegex(arch, r'name="country"[^>]*optional="show"', model)
