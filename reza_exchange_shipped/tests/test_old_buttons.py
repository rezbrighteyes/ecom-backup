# -*- coding: utf-8 -*-
"""The core Return / Credit Note / Reverse and Create Invoice buttons are
hidden from staff outside "Returns: old buttons" for customer documents only.

Each test reads the form as the user's browser gets it (get_views as that
user), so a button removed by `groups` is really absent, not just hidden."""
from lxml import etree

from odoo.tests import TransactionCase, new_test_user, tagged

GROUP = "reza_exchange_shipped.group_old_return_buttons"
STAFF_GROUPS = ("base.group_user,stock.group_stock_user,account.group_account_manager,"
                "sales_team.group_sale_salesman_all_leads")


@tagged("post_install", "-at_install")
class TestOldButtons(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff = new_test_user(cls.env, login="reza_uts_old_staff", groups=STAFF_GROUPS)
        cls.member = new_test_user(cls.env, login="reza_uts_old_member",
                                   groups=STAFF_GROUPS + "," + GROUP)

    def _buttons(self, user, model, view_type, name):
        arch = self.env[model].with_user(user).get_views([(False, view_type)])["views"][view_type]["arch"]
        return etree.fromstring(arch).xpath("//button[@name='%s']" % name)

    def _return_buttons(self, user):
        action = self.env.ref("stock.act_stock_return_picking")
        return self._buttons(user, "stock.picking", "form", str(action.id))

    def _wizard_buttons(self, user, name):
        view = self.env.ref("account.view_account_move_reversal")
        arch = self.env["account.move.reversal"].with_user(user).get_views(
            [(view.id, "form")])["views"]["form"]["arch"]
        return etree.fromstring(arch).xpath("//button[@name='%s']" % name)

    def test_staff_lose_customer_return_and_credit(self):
        # Return: one button, never on a customer delivery.
        buttons = self._return_buttons(self.staff)
        self.assertEqual(len(buttons), 1)
        self.assertIn("picking_type_code == 'outgoing'", buttons[0].get("invisible"))
        # Credit Note: one button, vendor bills only.
        buttons = self._buttons(self.staff, "account.move", "form", "action_reverse")
        self.assertEqual(len(buttons), 1)
        self.assertIn("move_type != 'in_invoice'", buttons[0].get("invisible"))
        self.assertNotIn("out_invoice", buttons[0].get("invisible"))
        # Wizard: no "Reverse and Create Invoice"; Reverse not for customer invoices.
        self.assertFalse(self._wizard_buttons(self.staff, "modify_moves"))
        buttons = self._wizard_buttons(self.staff, "refund_moves")
        self.assertEqual(len(buttons), 1)
        for move_type in ("'out_invoice'", "'out_refund'", "'some_invoice'"):
            self.assertIn(move_type, buttons[0].get("invisible"))

    def test_members_keep_the_originals_once(self):
        buttons = self._return_buttons(self.member)
        self.assertEqual(len(buttons), 1)
        # The original (another module on the database sets its invisible to
        # "0"), not our staff copy.
        self.assertNotIn("outgoing", buttons[0].get("invisible") or "")
        buttons = self._buttons(self.member, "account.move", "form", "action_reverse")
        self.assertEqual(len(buttons), 1)
        self.assertIn("out_invoice", buttons[0].get("invisible"))
        self.assertEqual(len(self._wizard_buttons(self.member, "modify_moves")), 1)
        buttons = self._wizard_buttons(self.member, "refund_moves")
        self.assertEqual(len(buttons), 1)
        self.assertFalse(buttons[0].get("invisible"))

    def test_first_members_by_login(self):
        group = self.env.ref(GROUP)
        self.assertIn(self.env.ref("base.user_admin"), group.users)
        logins = ["reza@brighteyes.com.au", "luke@brighteyes.com.au", "accounts@brighteyes.com.au"]
        users = self.env["res.users"].search([("login", "in", logins)])
        self.assertTrue(users, "the database copy has none of the logins: the test proves nothing")
        self.assertEqual(users - group.users, self.env["res.users"])
        # Ordinary staff are not members.
        others = self.env["res.users"].search([("share", "=", False), ("id", "not in", (users | self.env.ref("base.user_admin")).ids),
                                               ("login", "not like", "reza_uts_%")])
        self.assertFalse(others & group.users)
