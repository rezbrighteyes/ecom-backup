from odoo import fields, models, api,  SUPERUSER_ID, _
from user_agents import parse
from odoo.http import request
from datetime import datetime,timedelta

class res_users(models.Model):
    _inherit = 'res.users'

    login_log_ids = fields.One2many('login.log', 'user_id', 'Sessions')

    def action_kill_all_session(self):
        for record in self:
            return record.login_log_ids.logout_button()

    # Odoo 20: _login is an INSTANCE method (odoo/addons/base/models/
    # res_users.py `def _login(self, credential, user_agent_env)`), called on
    # the request's own env. The session row is written on that cursor inside
    # a savepoint, so a fault here can never abort the login transaction.
    def _login(self, credential, user_agent_env):
        res = super()._login(credential, user_agent_env)
        if not request:
            # XML-RPC / JSON-RPC: dispatch_rpc() removes the request, and
            # there is no browser session to record.
            return res
        try:
            with self.env.cr.savepoint():
                env = self.env(su=True)
                login_log_obj = env['login.log'].sudo()

                if not env['res.users'].sudo().browse(res.get('uid')).has_group('base.group_portal'):
                    user_agent = parse(request.httprequest.environ.get('HTTP_USER_AGENT', ''))
                    device = user_agent.device.family
                    if user_agent.device.family == 'Other':
                        if user_agent.is_pc:
                            device = 'PC'
                        elif user_agent.is_mobile:
                            device = 'Mobile'
                        elif user_agent.is_tablet:
                            device = 'Tablet'

                    if not login_log_obj.search([('user_agent','=',request.session.sid)], limit=1).id:
                        login_log = login_log_obj.create({
                            'login_date':datetime.now(),
                            'user_id':res.get('uid'),
                            'user_agent':request.session.sid,
                            'state':'active',
                            'browser':user_agent.browser.family,
                            'device':device,
                            'os':user_agent.os.family,
                        })
                        config_parameter_obj = env['ir.config_parameter'].sudo()
                        active_timeout = config_parameter_obj.get_str('advanced_session_management.session_timeout_active') or 'none'
                        if active_timeout != 'none':
                            interval_number = config_parameter_obj.get_int('advanced_session_management.session_timeout_interval_number')
                            if interval_number:
                                login_log.sudo().timeout_date = datetime.now() + timedelta(days=interval_number)

        except Exception:
            pass
        return res
            
