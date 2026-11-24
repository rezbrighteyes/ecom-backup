from odoo import api, fields, models, _
from odoo.http import request
from odoo.http.session import session_store
from odoo.tools import SQL
import base64
import csv
import io
import json
from datetime import datetime, timedelta

class ResDevice(models.Model):
    _inherit = 'res.device'

    # Odoo 20: res.device no longer inherits res.device.log (18 did), so the
    # fields the Sessions views show are declared here. res.session inherits
    # res.device and picks them up too. A device row's id IS a res.device.log
    # id, but activity rows point at whichever log of the session was found,
    # so they are matched on the session identifier.
    activity_log_ids = fields.Many2many(
        "activity.log", string="Activity Logs", compute="_compute_activity_log_ids")
    is_active = fields.Boolean("Is Active", compute="_compute_is_active")

    def _compute_activity_log_ids(self):
        identifiers = [i for i in self.mapped("session_identifier") if i]
        logs = self.env["activity.log"]
        if identifiers:
            logs = logs.search([("device_id.session_identifier", "in", identifiers)])
        for record in self:
            record.activity_log_ids = logs.filtered(
                lambda l: l.device_id.session_identifier == record.session_identifier)

    def _compute_is_active(self):
        for record in self:
            record.is_active = bool(
                record.last_activity and not record.revoked
                and (datetime.now() - record.last_activity) < timedelta(minutes=5))

    def dummy_btn(self):
        pass

    @property
    def _query(self):
        """Core's query (odoo/addons/base/models/res_device.py, ResDevice._query)
        plus revoked devices whose last activity is inside the retention window,
        so a revoked session stays visible for the retention period. Odoo 18
        did this through _where(), which 20 no longer has. The cutoff is fixed
        when the view is (re)built, as it was on 18."""
        config_parameter_obj = self.env['ir.config_parameter'].sudo()
        value = config_parameter_obj.search([('key', '=', 'advanced_session_management.remove_sesions')], limit=1)
        try:
            retention_days = max(int(value.value), 365) if value and value.value else 365
        except ValueError:
            retention_days = 365
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        return SQL("""
            SELECT
                L1.id,
                L1.session_identifier,
                L1.user_id,
                L1.ip_address,
                L1.user_agent,
                L1.country,
                L1.city,
                L1.first_activity,
                L1.last_activity,
                L1.revoked
            FROM res_device_log L1
            WHERE
                (L1.revoked IS NOT TRUE OR L1.last_activity >= %s)
                AND NOT ( EXISTS (
                    SELECT 1
                    FROM
                        res_device_log L2
                    WHERE
                        L2.user_id = L1.user_id
                        AND L2.session_identifier = L1.session_identifier
                        AND L2.ip_address = L1.ip_address
                        AND L2.user_agent = L1.user_agent
                        AND L2.id > L1.id
                        AND L2.revoked IS NOT TRUE
                ))
        """, cutoff_date)


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

    @api.private
    def session_timeout_ah(self):
        config_parameter_obj = self.env["ir.config_parameter"].sudo()
        active_timeout = config_parameter_obj.get_str(
            "advanced_session_management.session_timeout_active"
        )

        interval_number = config_parameter_obj.get_int(
            "advanced_session_management.session_timeout_interval_number", 0
        )
        interval_type = config_parameter_obj.get_str(
            "advanced_session_management.session_timeout_interval_type", "hours"
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
            # Odoo 20: res.device.log.user_id is an Integer, not a Many2one.
            user = self.env["res.users"].sudo().browse(session.user_id).exists()
            if not user or not user._is_internal():
                continue
            if user.has_group(
                "advanced_session_management.group_login_log_admin_ah"
            ):
                continue

            if session.last_activity:
                expire_time = session.last_activity + timeout_delta

                if expire_time < now:
                    if active_timeout == "active":
                        if not session.is_active:
                            session._asm_revoke()
                    elif active_timeout == "inactive":
                        session._asm_revoke()

    def _asm_revoke(self):
        """End these sessions: delete the session files and mark every log of
        them revoked. Odoo 18 did this with res.device._revoke(); on 20 that
        method lives on res.session and also logs out the CURRENT request,
        which a cron does not have."""
        identifiers = list(dict.fromkeys(i for i in self.mapped("session_identifier") if i))
        if not identifiers:
            return
        session_store().delete_from_identifiers(identifiers)
        self.sudo().search([
            ("session_identifier", "in", identifiers), ("revoked", "=", False),
        ]).write({"revoked": True})

    @api.private
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
        # Odoo 20 has no is_current on res.device.log; same test as 18's.
        current_sid = ""
        try:
            current_sid = (request and request.session.sid) or ""
        except Exception:  # noqa: BLE001 - no request / no session
            current_sid = ""
        device_logs = device_logs.filtered(
            lambda d: not (current_sid and d.session_identifier
                           and current_sid.startswith(d.session_identifier)))
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

        device_users = {
            u.id: (u.display_name, u.login)
            for u in self.env["res.users"].sudo().with_context(active_test=False).browse(
                list(set(device_logs.mapped("user_id")))).exists()
        }
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
                    "user": device_users.get(log.user_id, (str(log.user_id), ""))[0],
                    "user_login": device_users.get(log.user_id, ("", ""))[1],
                    "platform": field_value(log, "platform"),
                    "browser": field_value(log, "browser"),
                    "ip_address": field_value(log, "ip_address"),
                    "session_identifier": field_value(log, "session_identifier"),
                    "revoked": field_value(log, "revoked"),
                    "user_agent": field_value(log, "user_agent"),
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
                "user_agent",
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
                "user_agent": log["user_agent"],
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
