from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestWizardAccess(TransactionCase):
    """The wizard writes website_ids under sudo. On Odoo 18 its access row had
    no group, so any signed-in user (a portal shopper included) could call it
    over RPC and move any product off every shop."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env["website"].create({"name": "Wizard Test Site"})
        cls.product = cls.env["product.template"].create({"name": "Wizard Test Shade"})
        cls.portal = new_test_user(cls.env, login="sh_wiz_portal", groups="base.group_portal")
        cls.staff = new_test_user(cls.env, login="sh_wiz_staff", groups="base.group_user")
        cls.manager = new_test_user(cls.env, login="sh_wiz_manager",
                                    groups="base.group_user,product.group_product_manager")

    def _run(self, user):
        Wizard = self.env["sh.product.multi.website"].with_user(user).with_context(
            active_ids=self.product.ids)
        Wizard.create({"website_ids": [(6, 0, self.site.ids)]}).action_update()

    def test_portal_user_cannot_change_websites(self):
        with self.assertRaises(AccessError):
            self._run(self.portal)
        self.assertFalse(self.product.website_ids)

    def test_plain_staff_cannot_change_websites(self):
        with self.assertRaises(AccessError) as cm:
            self._run(self.staff)
        self.assertIn("Only product managers", str(cm.exception))
        self.assertFalse(self.product.website_ids)

    def test_product_manager_can(self):
        self._run(self.manager)
        self.assertEqual(self.product.website_ids, self.site)
