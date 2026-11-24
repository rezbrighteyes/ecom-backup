from odoo.exceptions import AccessError
from odoo.service.model import get_public_method
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRpcPrivate(TransactionCase):
    """These methods run under sudo and are meant for crons and install
    data only. Over RPC any signed-in user, a portal customer included, could
    call them: shown on a copy of production, a customer reset the session
    settings and then deleted 417 rows of login history. `get_public_method`
    is the exact gate /xmlrpc and call_kw use."""

    CRON_ONLY = [
        ("res.device.log", "remove_old_log"),
        ("res.device.log", "session_timeout_ah"),
        ("login.log", "session_timeout_ah"),
        ("login.log", "remove_old_log"),
        ("ir.config_parameter", "apply_advanced_session_management_cron_settings"),
        ("ir.config_parameter", "delete_record_ao"),
    ]

    def test_cron_only_methods_cannot_be_called_remotely(self):
        for model, method in self.CRON_ONLY:
            with self.subTest(model=model, method=method):
                with self.assertRaises(AccessError) as cm:
                    get_public_method(self.env[model], method)
                self.assertIn("cannot be called remotely", str(cm.exception))

    def test_the_crons_still_run_them(self):
        """@api.private blocks RPC only; the cron code calls them directly."""
        self.env["res.device.log"].remove_old_log()
        self.env["ir.config_parameter"].delete_record_ao()

    def test_control_a_normal_button_is_still_callable(self):
        # Control: the gate does admit an ordinary public method, so the
        # refusals above are about the decorator, not a broken check.
        self.assertTrue(get_public_method(self.env["login.log"], "logout_button"))
