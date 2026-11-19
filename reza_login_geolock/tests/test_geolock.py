from unittest.mock import patch

from odoo.exceptions import AccessDenied, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.reza_login_geolock.models import res_users as geo

MOD = "odoo.addons.reza_login_geolock.models.res_users"


@tagged("post_install", "-at_install")
class TestStaffGeolock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff = cls.env["res.users"].create({
            "name": "Geolock Staff", "login": "geolock.staff.test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
        })
        cls.portal = cls.env["res.users"].create({
            "name": "Geolock Portal", "login": "geolock.portal.test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_portal").id])],
        })
        cls.params = cls.env["ir.config_parameter"].sudo()
        cls.params.set_param(geo.PARAM_COUNTRIES, "AU")

    def _events(self, user):
        return self.env["reza.login.geolock.event"].search([("user_id", "=", user.id)])

    def _rpc_check(self, user, password):
        """res.users.check() (the per-call RPC password check) opens its own
        cursor in Odoo 18. Point the registry at the test transaction for the
        call, as core's ir.cron tests do, so it sees the test user and writes
        nothing outside the test."""
        self.env.flush_all()
        self.registry.enter_test_mode(self.cr)
        try:
            self.env["res.users"].check(self.cr.dbname, user.id, password)
        finally:
            self.registry.leave_test_mode()
            self.env.invalidate_all()

    def _check(self, user, mode, country, channel="web"):
        self.params.set_param(geo.PARAM_MODE, mode)
        with patch(MOD + "._client", return_value=("203.0.113.9", "test-agent")), \
                patch(MOD + "._country_of", return_value=country):
            user._reza_geolock_check(channel)

    def test_block_mode_refuses_staff_from_overseas(self):
        with self.assertRaisesRegex(AccessDenied, "not allowed from this country"):
            self._check(self.staff, "block", "US")
        event = self._events(self.staff)
        self.assertEqual(len(event), 1)
        self.assertEqual((event.action, event.country, event.channel, event.ip),
                         ("blocked", "US", "web", "203.0.113.9"))

    def _allow(self, name, users=None, active=True):
        return self.env["reza.login.geolock.ip"].create({
            "name": name, "active": active,
            "user_ids": [(6, 0, users.ids)] if users else False,
        })

    def test_allowed_ip_lets_staff_in_from_overseas(self):
        self._allow("203.0.113.0/24")
        self._check(self.staff, "block", "GB")
        self.assertFalse(self._events(self.staff))

    def test_allowed_ip_for_another_user_still_blocks(self):
        other = self.staff.copy({"login": "geolock.other.test"})
        self._allow("203.0.113.9", users=other)
        with self.assertRaises(AccessDenied):
            self._check(self.staff, "block", "GB")
        self._check(other, "block", "GB")

    def test_archived_allowed_ip_does_not_count(self):
        self._allow("203.0.113.9", active=False)
        with self.assertRaises(AccessDenied):
            self._check(self.staff, "block", "GB")

    def test_allowed_ip_ipv6_range_and_validation(self):
        rec = self._allow("2a00:23c7:d7db:2501:7817:2c1b:b4bc:14e7/56")
        self.assertEqual(rec.name, "2a00:23c7:d7db:2500::/56")
        model = self.env["reza.login.geolock.ip"]
        self.assertTrue(model._reza_allows("2a00:23c7:d7db:25ff::1", self.staff))
        self.assertFalse(model._reza_allows("2a00:23c7:d7db:2600::1", self.staff))
        self.assertFalse(model._reza_allows("203.0.113.9", self.staff))
        with self.assertRaises(ValidationError):
            self._allow("not an address")

    def _lock(self, user):
        user.reza_geolock_ip_only = True
        return user

    def test_ip_lock_refuses_unlisted_address_even_in_australia(self):
        self._lock(self.staff)
        with self.assertRaisesRegex(AccessDenied, "approved addresses"):
            self._check(self.staff, "block", "AU")
        event = self._events(self.staff)
        self.assertEqual((event.action, event.country), ("held", "AU"))

    def test_ip_lock_beats_exemption_and_off_mode(self):
        self._lock(self.staff).reza_geolock_exempt = True
        with self.assertRaises(AccessDenied):
            self._check(self.staff, "off", "AU")
        with self.assertRaises(AccessDenied):
            self._check(self.staff, "report", None)

    def test_ip_lock_lets_listed_address_in(self):
        self._lock(self.staff)
        self._allow("203.0.113.9", users=self.staff)
        self._check(self.staff, "block", "GB")
        self.assertFalse(self._events(self.staff))

    def test_ip_lock_ignores_archived_and_other_users_entries(self):
        self._lock(self.staff)
        other = self.staff.copy({"login": "geolock.other2.test"})
        self._allow("203.0.113.9", users=self.staff, active=False)
        self._allow("203.0.113.0/24", users=other)
        with self.assertRaises(AccessDenied):
            self._check(self.staff, "block", "AU")

    def test_ip_lock_entry_for_everyone_counts(self):
        self._lock(self.staff)
        self._allow("203.0.113.9")
        self._check(self.staff, "block", "AU")

    def test_ip_lock_breach_is_emailed(self):
        if "mail.mail" not in self.env:
            self.skipTest("mail not installed")
        self.params.set_param(geo.PARAM_ALERT_TO, "it@example.com")
        self._lock(self.staff)
        mails = self.env["mail.mail"].sudo()
        before = mails.search_count([])
        # Not assertRaises: Odoo's version rolls back to a savepoint, which
        # would take the queued mail with it.
        with self.assertRaisesRegex(AccessDenied, "approved addresses"):
            self._check(self.staff, "block", "AU")
        mail = mails.search([], order="id desc", limit=1)
        self.assertEqual(mails.search_count([]), before + 1)
        self.assertIn("IP lock breach", mail.subject)
        self.assertEqual(mail.email_to, "it@example.com")

    def test_plain_users_are_unaffected_by_ip_lock(self):
        self._check(self.staff, "block", "AU")
        self.assertFalse(self._events(self.staff))

    def test_report_mode_records_but_allows(self):
        self._check(self.staff, "report", "US")
        self.assertEqual(self._events(self.staff).action, "would_block")

    def test_australia_is_allowed(self):
        self._check(self.staff, "block", "AU")
        self.assertFalse(self._events(self.staff))

    def test_portal_users_are_never_checked(self):
        self._check(self.portal, "block", "US")
        self.assertFalse(self._events(self.portal))

    def test_exempt_staff_is_allowed(self):
        self.staff.reza_geolock_exempt = True
        self._check(self.staff, "block", "US")
        self.assertFalse(self._events(self.staff))

    def test_unknown_or_private_address_is_allowed(self):
        self._check(self.staff, "block", None)
        self.assertFalse(self._events(self.staff))

    def test_off_does_nothing(self):
        self._check(self.staff, "off", "US")
        self.assertFalse(self._events(self.staff))

    def test_no_http_client_is_not_judged(self):
        self.params.set_param(geo.PARAM_MODE, "block")
        with patch(MOD + "._client", return_value=None), patch(MOD + "._country_of", return_value="US"):
            self.staff._reza_geolock_check("rpc")
        self.assertFalse(self._events(self.staff))

    def test_repeated_attempts_record_one_event_per_hour(self):
        for _i in range(3):
            self._check(self.staff, "report", "US", channel="rpc")
        self.assertEqual(len(self._events(self.staff)), 1)

    def test_extra_allowed_country(self):
        self.params.set_param(geo.PARAM_COUNTRIES, "AU, nz")
        self._check(self.staff, "block", "NZ")
        self.assertFalse(self._events(self.staff))

    def test_private_and_loopback_addresses_have_no_country(self):
        for ip in ("10.0.3.7", "127.0.0.1", "192.168.1.77", "::1", "", "not-an-ip"):
            self.assertIsNone(geo._country_of(ip), ip)

    def test_rpc_password_check_is_geolocked_on_every_call(self):
        """res.users.check is cached after the first call; the geolock must not be."""
        self.staff.password = "Geolock-test-pw-1"
        self.params.set_param(geo.PARAM_MODE, "block")
        with patch(MOD + "._client", return_value=("203.0.113.9", "")):
            with patch(MOD + "._country_of", return_value="AU"):
                self._rpc_check(self.staff, "Geolock-test-pw-1")
            with patch(MOD + "._country_of", return_value="US"), \
                    self.assertRaisesRegex(AccessDenied, "not allowed from this country"):
                self._rpc_check(self.staff, "Geolock-test-pw-1")

    def test_wrong_password_is_not_recorded(self):
        self.staff.password = "Geolock-test-pw-1"
        self.params.set_param(geo.PARAM_MODE, "block")
        # Odoo's assertRaises rolls back a savepoint, which would hide an
        # event; catch the exception by hand so the check below means something.
        with patch(MOD + "._client", return_value=("203.0.113.9", "")), \
                patch(MOD + "._country_of", return_value="US"):
            try:
                self._rpc_check(self.staff, "wrong")
            except AccessDenied as e:
                self.assertNotIn("country", str(e))
            else:
                self.fail("a wrong password was accepted")
        self.assertFalse(self._events(self.staff))

    def test_bearer_api_key_is_geolocked(self):
        key = self.env["res.users.apikeys"].with_user(self.staff).sudo()._generate(None, "geolock test", None)
        self.params.set_param(geo.PARAM_MODE, "block")
        with patch(MOD + "._client", return_value=("203.0.113.9", "")), \
                patch(MOD + "._country_of", return_value="US"), \
                self.assertRaisesRegex(AccessDenied, "not allowed from this country"):
            self.env["res.users.apikeys"]._check_credentials(scope="rpc", key=key)
        self.assertEqual(self._events(self.staff).channel, "apikey")

    def test_empty_recordset_password_recheck_does_not_crash(self):
        """change_password and the portal security pages call _check_credentials
        on an empty recordset; the check must resolve the env user, not crash."""
        self.params.set_param(geo.PARAM_MODE, "report")
        with patch(MOD + "._client", return_value=("203.0.113.9", "")), \
                patch(MOD + "._country_of", return_value="US"):
            self.env["res.users"].with_user(self.portal)._reza_geolock_check("web")
            self.env["res.users"].with_user(self.staff)._reza_geolock_check("web")
        self.assertFalse(self._events(self.portal))
        self.assertEqual(self._events(self.staff).action, "would_block")

    def test_portal_change_password_from_overseas_works(self):
        self.portal.password = "Geolock-portal-pw-1"
        self.params.set_param(geo.PARAM_MODE, "block")
        with patch(MOD + "._client", return_value=("203.0.113.9", "")), \
                patch(MOD + "._country_of", return_value="US"):
            self.env["res.users"].with_user(self.portal).change_password("Geolock-portal-pw-1", "Geolock-portal-pw-2")

    def test_a_fault_in_the_check_lets_the_user_in(self):
        self.params.set_param(geo.PARAM_MODE, "block")
        with patch(MOD + "._client", return_value=("203.0.113.9", "")), \
                patch(MOD + "._country_of", side_effect=RuntimeError("geoip broke")):
            self.staff._reza_geolock_check("web")
        self.assertFalse(self._events(self.staff))

    def test_administrator_is_exempt_from_install(self):
        admin = self.env.ref("base.user_admin")
        self.assertTrue(admin.reza_geolock_exempt)
        self._check(admin, "block", "US")
        self.assertFalse(self._events(admin))

    def test_only_the_administrator_manages_the_geolock(self):
        group = self.env.ref("reza_login_geolock.group_geolock_manager")
        # Odoo 18 stores implied memberships in res.groups.users itself.
        self.assertIn(self.env.ref("base.user_admin"), group.users)
        self.assertNotIn(self.staff, group.users)
        menu = self.env.ref("reza_login_geolock.menu_reza_login_geolock_event")
        self.assertEqual(menu.groups_id, group)


@tagged("post_install", "-at_install")
class TestStaffGeolockSession(HttpCase):

    def test_open_session_is_ended_from_overseas(self):
        user = self.env["res.users"].create({
            "name": "Geolock Session", "login": "geolock.session.test", "password": "Geolock-sess-pw-1",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        params = self.env["ir.config_parameter"].sudo()
        params.set_param(geo.PARAM_MODE, "block")
        params.set_param(geo.PARAM_COUNTRIES, "AU")
        with patch(MOD + "._country_of", return_value="AU"):
            self.authenticate("geolock.session.test", "Geolock-sess-pw-1")
            ok = self.url_open("/odoo", allow_redirects=False)
            self.assertNotIn("/web/login", ok.headers.get("Location", ""))
        # The verdict is cached per address and setting; the test server's
        # address never changes, so change the setting to force a fresh look.
        params.set_param(geo.PARAM_COUNTRIES, "AU,NZ")
        with patch(MOD + "._country_of", return_value="US"):
            res = self.url_open("/odoo", allow_redirects=False)
        self.assertIn("/web/login", res.headers.get("Location", ""))
        # The session is gone: back in Australia it still has to log in again.
        with patch(MOD + "._country_of", return_value="AU"):
            again = self.url_open("/odoo", allow_redirects=False)
        self.assertIn("/web/login", again.headers.get("Location", ""))
        self.assertTrue(user)
