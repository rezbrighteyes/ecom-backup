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

    # Odoo 18: _login is a CLASSMETHOD taking the database name (Odoo 19 made
    # it an instance method). There is no env on the class, so the session
    # row is written through its own cursor, committed on leaving the block.
    @classmethod
    def _login(cls, db, credential, user_agent_env):
        res = super()._login(db, credential, user_agent_env)
        try:
            with cls.pool.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
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
                            # 'ip':ip,
                            'browser':user_agent.browser.family,
                            # 'session_id':request.session.sid,
                            'device':device,
                            'os':user_agent.os.family,
                            # 'country':country,
                            # 'loc_state':state,
                            # 'city':city
                        })
                        config_parameter_obj = env['ir.config_parameter'].sudo()
                        active_timeout = config_parameter_obj.get_param('advanced_session_management.session_timeout_active') or 'none'
                        if active_timeout != 'none':
                            interval_number = int(config_parameter_obj.get_param('advanced_session_management.session_timeout_interval_number'))
                            if interval_number:
                                login_log.sudo().timeout_date = datetime.now() + timedelta(days=interval_number)
                                # login_log.sudo().write({'timeout_date':datetime.now() + timedelta(hours=interval_number)})

        except:
            pass
        return res
            
