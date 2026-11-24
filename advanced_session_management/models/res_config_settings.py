from odoo import api, fields, models, _
from datetime import datetime, timedelta


class res_config_settings(models.TransientModel):
    _inherit = "res.config.settings"

    remove_sesions = fields.Integer("Scheduled remove old sessions", default=365)
    send_mail = fields.Boolean("Send Mail When New Session Start", default=True)
    session_timeout_interval_number = fields.Integer("Interval Number", default=0)
    session_timeout_interval_type = fields.Selection(
        [("minutes", "Minutes"), ("hours", "Hours"), ("days", "Days")],
        string="Interval Unit",
        default="hours",
    )
    session_timeout_active = fields.Selection(
        [("none", "None"), ("active", "Active"), ("inactive", "Inactive")],
        string="Do not timeout active session",
        default="none",
    )

    @api.model
    def get_values(self):
        res = super(res_config_settings, self).get_values()
        config_parameter_obj = self.env["ir.config_parameter"].sudo()
        res["remove_sesions"] = config_parameter_obj.get_int(
            "advanced_session_management.remove_sesions", 365
        )
        if res["remove_sesions"] < 365:
            res["remove_sesions"] = 365
        res["send_mail"] = (
            config_parameter_obj.get_str(
                "advanced_session_management.send_mail", "False"
            )
            == "True"
        )

        res["session_timeout_interval_number"] = config_parameter_obj.get_int(
            "advanced_session_management.session_timeout_interval_number", 0
        )
        res["session_timeout_interval_type"] = config_parameter_obj.get_str(
            "advanced_session_management.session_timeout_interval_type", "hours"
        )
        res["session_timeout_active"] = config_parameter_obj.get_str(
            "advanced_session_management.session_timeout_active", "none"
        )

        return res

    @api.model
    def set_values(self):
        config_parameter_obj = self.env["ir.config_parameter"].sudo()

        if self.remove_sesions <= 0:
            remove_sesions = 365
        else:
            remove_sesions = max(self.remove_sesions, 365)
        config_parameter_obj.set_str(
            "advanced_session_management.remove_sesions", remove_sesions
        )
        config_parameter_obj.set_str(
            "advanced_session_management.send_mail", str(self.send_mail)
        )

        config_parameter_obj.set_str(
            "advanced_session_management.session_timeout_interval_number",
            str(self.session_timeout_interval_number or 0),
        )
        config_parameter_obj.set_str(
            "advanced_session_management.session_timeout_interval_type",
            self.session_timeout_interval_type or "hours",
        )

        active_timeout = self.session_timeout_active
        if active_timeout in ["active", "inactive"]:
            interval_number = self.session_timeout_interval_number or 0
            interval_type = self.session_timeout_interval_type or "hours"

            if interval_type == "minutes":
                total_timeout_minutes = interval_number
            elif interval_type == "hours":
                total_timeout_minutes = interval_number * 60
            else:
                total_timeout_minutes = interval_number * 1440

            if total_timeout_minutes > 0:
                login_logs = (
                    self.env["login.log"].sudo().search([("state", "=", "active")])
                )
                for login_log in login_logs:
                    login_log.timeout_date = datetime.now() + timedelta(
                        minutes=total_timeout_minutes
                    )
        else:
            login_logs = self.env["login.log"].sudo().search([("state", "=", "active")])
            for login_log in login_logs:
                login_log.timeout_date = False

        config_parameter_obj.set_str(
            "advanced_session_management.session_timeout_active",
            self.session_timeout_active,
        )

        return super(res_config_settings, self).set_values()


class ir_config_parameter(models.Model):
    _inherit = "ir.config_parameter"

    def delete_record_ao(self):
        self.search([("key", "=", "disable_log")], limit=1).unlink()

    @api.model
    def apply_advanced_session_management_cron_settings(self):
        session_timeout = self.env.ref(
            "advanced_session_management.session_timeout_ah", raise_if_not_found=False
        )
        if session_timeout:
            session_timeout.sudo().write({
                "active": True,
                "interval_number": 10,
                "interval_type": "minutes",
            })

        enable_log = self.env.ref(
            "advanced_session_management.enable_user_activity_log", raise_if_not_found=False
        )
        if enable_log:
            enable_log.sudo().write({"active": False})

        self.sudo().set_str("advanced_session_management.remove_sesions", "365")
