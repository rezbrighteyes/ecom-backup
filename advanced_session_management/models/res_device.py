from odoo import api, fields, models, _
from odoo.http import request
import base64
import csv
import io
import json
from datetime import datetime, timedelta

class ResDevice(models.Model):
    _inherit = 'res.device'

    @api.model
    def _where(self):
        config_parameter_obj = self.env['ir.config_parameter'].sudo()
        value = config_parameter_obj.search([('key', '=', 'advanced_session_management.remove_sesions')], limit=1)
        if value and value.value:
            retention_days = max(int(value.value), 365)
        else:
            retention_days = 365
        
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime('%Y-%m-%d %H:%M:%S')
        
        return f"""
            WHERE
                NOT EXISTS (
                    SELECT 1
                    FROM res_device_log D2
                    WHERE
                        D2.user_id = D.user_id
                        AND D2.session_identifier = D.session_identifier
                        AND D2.platform IS NOT DISTINCT FROM D.platform
                        AND D2.browser IS NOT DISTINCT FROM D.browser
                        AND (
                            D2.last_activity > D.last_activity
                            OR (D2.last_activity = D.last_activity AND D2.id > D.id)
                        )
                        AND D2.revoked = False
                )
                AND (
                    D.revoked = False
                    OR (D.revoked = True AND D.last_activity >= '{cutoff_date}')
                )
        """

class ResDeviceLog(models.Model):
    _inherit = "res.device.log"

    activity_log_ids = fields.One2many("activity.log", "device_id", "Activity Logs")
    is_active = fields.Boolean("Is Active", compute="_compute_is_active")

    @api.model
    def _reza_current_device_log(self, uid=None):
        """This session's device log, WITHOUT searching a non-stored field.

        `res.device.log.is_current` is a COMPUTE (core `res_device.py:34`:
        `request and request.session.sid.startswith(device.session_identifier)`),
        so putting it in a domain raises

            ValueError: Cannot convert res.device.log.is_current to SQL
            because it is not stored

        This module did exactly that in four places, each as the fallback when
        the `session_identifier` lookup missed. On Odoo 19 that fallback is not
        a fallback, it is a 500 — and one of the four is `/web/session/logout`,
        so a portal user who reached it could not log out at all. Reported by
        Luke 2026-08-10 and reproduced from the production log.

        The intent is preserved rather than dropped: core's own definition is
        "the device whose session_identifier is a prefix of my sid", so that is
        what is matched, in Python, over a small stored-field search.
        """
        if not request:
            return self.browse()
        try:
            sid = request.session.sid or ""
        except Exception:  # noqa: BLE001 - no session, no current device
            return self.browse()
        if not sid:
            return self.browse()
        candidates = self.sudo().search(
            [("user_id", "=", uid or self.env.uid), ("revoked", "=", False)],
            order="last_activity desc", limit=50,
        )
        current = candidates.filtered(
            lambda d: d.session_identifier and sid.startswith(d.session_identifier))
        return current[:1]

    def _compute_is_active(self):
        for record in self:
            if record.last_activity and not record.revoked:
                record.is_active = (datetime.now() - record.last_activity) < timedelta(
                    minutes=5
                )
            else:
                record.is_active = False

    def session_timeout_ah(self):
        config_parameter_obj = self.env["ir.config_parameter"].sudo()
        active_timeout = config_parameter_obj.get_param(
            "advanced_session_management.session_timeout_active"
        )

        interval_number = int(
            config_parameter_obj.get_param(
                "advanced_session_management.session_timeout_interval_number", default=0
            )
        )
        interval_type = config_parameter_obj.get_param(
            "advanced_session_management.session_timeout_interval_type", default="hours"
        )

        if active_timeout == "none" or interval_number <= 0:
            return

        if interval_type == "minutes":
            timeout_delta = timedelta(minutes=interval_number)
        elif interval_type == "hours":
            timeout_delta = timedelta(hours=interval_number)
        elif interval_type == "days":
            timeout_delta = timedelta(days=interval_number)
        else:
            timeout_delta = timedelta(hours=interval_number)

        now = datetime.now()

        active_sessions = self.search([("revoked", "=", False)])

        for session in active_sessions:
            # Staff sessions only: on ecom most rows are shop customers
            # (portal), and a timeout must not sign them out of the shop.
            if not session.user_id._is_internal():
                continue
            if session.user_id.has_group(
                "advanced_session_management.group_login_log_admin_ah"
            ):
                continue

            if session.last_activity:
                expire_time = session.last_activity + timeout_delta

                if expire_time < now:
                    if active_timeout == "active":
                        if not session.is_active:
                            self.env["res.device"].browse(session.id)._revoke()
                    elif active_timeout == "inactive":
                        self.env["res.device"].browse(session.id)._revoke()

    def remove_old_log(self):
        config_parameter_obj = self.env["ir.config_parameter"].sudo()
        value = config_parameter_obj.search(
            [("key", "=", "advanced_session_management.remove_sesions")], limit=1
        )
        if value and value.value:
            retention_days = max(int(value.value), 365)
        else:
            retention_days = 365

        cutoff = datetime.now() - timedelta(days=retention_days)
        # `is_current` cannot go in a domain (compute, not stored). It is also
        # False for EVERY row when there is no request, which is the case in a
        # cron -- so the leaf only ever meant "do not delete the device I am
        # using right now". Filtered in Python to keep exactly that.
        device_logs = self.sudo().search([("last_activity", "<=", cutoff)])
        device_logs = device_logs.filtered(lambda d: not d.is_current)
        activity_logs = self.env["activity.log"].sudo().search([
            ("create_date", "<=", cutoff)
        ])

        self._backup_logs_before_cleanup(activity_logs, device_logs, cutoff, retention_days)

        device_logs.unlink()
        activity_logs.unlink()

    def _backup_logs_before_cleanup(self, activity_logs, device_logs, cutoff, retention_days):
        if not activity_logs and not device_logs:
            return

        def field_value(record, field_name):
            if field_name not in record._fields:
                return False
            value = record[field_name]
            if hasattr(value, "display_name"):
                return value.display_name
            return value

        payload = {
            "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
            "cutoff": fields.Datetime.to_string(cutoff),
            "retention_days": retention_days,
            "activity_logs": [
                {
                    "id": log.id,
                    "name": log.name,
                    "user": log.user_id.display_name,
                    "user_login": log.user_id.login,
                    "model": log.model,
                    "res_id": log.res_id,
                    "action": log.action,
                    "view": log.view,
                    "url": log.url,
                    "changes": log.value,
                    "edit_values": [
                        {
                            "name": edit_value.name,
                            "old": edit_value.old,
                            "new": edit_value.new,
                        }
                        for edit_value in log.edit_value_ids
                    ],
                    "device_id": log.device_id.id,
                    "create_date": fields.Datetime.to_string(log.create_date),
                }
                for log in activity_logs
            ],
            "device_logs": [
                {
                    "id": log.id,
                    "user": log.user_id.display_name,
                    "user_login": log.user_id.login,
                    "platform": field_value(log, "platform"),
                    "browser": field_value(log, "browser"),
                    "ip_address": field_value(log, "ip_address"),
                    "session_identifier": field_value(log, "session_identifier"),
                    "revoked": field_value(log, "revoked"),
                    "is_current": field_value(log, "is_current"),
                    "last_activity": fields.Datetime.to_string(log.last_activity),
                    "create_date": fields.Datetime.to_string(log.create_date),
                }
                for log in device_logs
            ],
        }

        filename = "advanced_session_management_cleanup_%s.json" % datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        self.env["ir.attachment"].sudo().create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(
                json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
            ).decode("ascii"),
            "mimetype": "application/json",
            "res_model": "res.company",
            "res_id": self.env.company.id,
        })

        csv_buffer = io.StringIO()
        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=[
                "type",
                "id",
                "name",
                "user",
                "user_login",
                "model",
                "res_id",
                "action",
                "view",
                "url",
                "changes",
                "device_id",
                "platform",
                "browser",
                "ip_address",
                "session_identifier",
                "revoked",
                "is_current",
                "last_activity",
                "create_date",
            ],
        )
        writer.writeheader()
        for log in payload["activity_logs"]:
            writer.writerow({
                "type": "activity",
                "id": log["id"],
                "name": log["name"],
                "user": log["user"],
                "user_login": log["user_login"],
                "model": log["model"],
                "res_id": log["res_id"],
                "action": log["action"],
                "view": log["view"],
                "url": log["url"],
                "changes": log["changes"],
                "device_id": log["device_id"],
                "create_date": log["create_date"],
            })
        for log in payload["device_logs"]:
            writer.writerow({
                "type": "device",
                "id": log["id"],
                "user": log["user"],
                "user_login": log["user_login"],
                "platform": log["platform"],
                "browser": log["browser"],
                "ip_address": log["ip_address"],
                "session_identifier": log["session_identifier"],
                "revoked": log["revoked"],
                "is_current": log["is_current"],
                "last_activity": log["last_activity"],
                "create_date": log["create_date"],
            })

        csv_filename = "advanced_session_management_cleanup_%s.csv" % datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        self.env["ir.attachment"].sudo().create({
            "name": csv_filename,
            "type": "binary",
            "datas": base64.b64encode(csv_buffer.getvalue().encode("utf-8")).decode("ascii"),
            "mimetype": "text/csv",
            "res_model": "res.company",
            "res_id": self.env.company.id,
        })

    def dummy_btn(self):
        pass
