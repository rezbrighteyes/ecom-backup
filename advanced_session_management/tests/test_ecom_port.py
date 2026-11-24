# -*- coding: utf-8 -*-
"""Ecom port: the activity log records staff, not shoppers, customers or crons."""

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEcomPort(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff = cls.env["res.users"].create({
            "name": "ASM Staff",
            "login": "asm_staff@example.com",
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id,
                                  cls.env.ref("base.group_partner_manager").id])],
        })
        cls.portal = cls.env["res.users"].create({
            "name": "ASM Customer",
            "login": "asm_portal@example.com",
            "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
        })
        cls.partner = cls.env["res.partner"].create({"name": "ASM Target"})
        cls.Log = cls.env["activity.log"].sudo()

    def _logs(self, action, record):
        return self.Log.search([
            ("model", "=", record._name),
            ("res_id", "=", str(record.id)),
            ("action", "=", action),
        ])

    def _as_session(self, uid):
        req = MockRequest(self.env)
        mocked = req.__enter__()
        mocked.session.uid = uid
        self.addCleanup(req.__exit__, None, None, None)
        return mocked

    def test_staff_edit_is_logged_with_the_change(self):
        self._as_session(self.staff.id)
        self.partner.with_user(self.staff).write({"ref": "NEW-REF"})
        log = self._logs("edit", self.partner)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.user_id, self.staff)
        self.assertIn("NEW-REF", log.value)

    def test_staff_create_and_delete_are_logged(self):
        self._as_session(self.staff.id)
        partner = self.env["res.partner"].with_user(self.staff).create({"name": "ASM New"})
        self.assertEqual(len(self._logs("create", partner)), 1)
        partner_id = partner.id
        partner.sudo().unlink()
        self.assertEqual(self.Log.search_count([
            ("model", "=", "res.partner"), ("res_id", "=", str(partner_id)),
            ("action", "=", "delete")]), 1)

    def test_sudo_write_is_credited_to_the_signed_in_staff(self):
        self._as_session(self.staff.id)
        self.partner.sudo().write({"ref": "SUDO-REF"})
        self.assertEqual(self._logs("edit", self.partner).user_id, self.staff)

    def test_shopper_with_no_login_is_not_logged(self):
        self._as_session(None)
        self.partner.sudo().write({"ref": "SHOP-REF"})
        self.env["res.partner"].sudo().create({"name": "ASM Shopper"})
        self.assertFalse(self._logs("edit", self.partner))

    def test_portal_customer_is_not_logged(self):
        self._as_session(self.portal.id)
        self.partner.sudo().write({"ref": "PORTAL-REF"})
        self.assertFalse(self._logs("edit", self.partner))

    def test_cron_with_no_request_is_not_logged(self):
        self.partner.write({"ref": "CRON-REF"})
        self.assertFalse(self._logs("edit", self.partner))

    def test_setting_value_is_never_copied_into_the_log(self):
        param = self.env["ir.config_parameter"].sudo().create({
            "key": "asm.test.secret", "value": "old-secret"})
        self._as_session(self.staff.id)
        param.write({"value": "new-secret"})
        log = self._logs("edit", param)
        self.assertEqual(len(log), 1)
        values = log.edit_value_ids.mapped("old") + log.edit_value_ids.mapped("new")
        self.assertTrue(values)
        self.assertNotIn("old-secret", values + [log.value or ""])
        self.assertNotIn("new-secret", values + [log.value or ""])
