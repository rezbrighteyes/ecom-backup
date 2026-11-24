from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
from odoo.http import request

from . import exclude_models

# Models whose changed VALUES must never be copied into the activity log.
SECRET_VALUE_MODELS = ('ir.config_parameter',)
HIDDEN = '(hidden)'

class BaseModel(models.AbstractModel):
    _inherit = 'base'

    def _asm_should_log(self):
        """Log only what a signed-in STAFF user does through the web client.

        Ecom is a shop: shoppers (public, no uid) and customers (portal) create
        and write orders, partners and payments all day, and crons such as the
        hourly Edbert stock sync write thousands of product rows with no
        request at all. Logging those buried the staff trail and added a
        module search, a field search per value and an insert to every write.
        The session's uid is used, not env.uid, so a sudo() write made on a
        staff member's behalf is still attributed to that person.
        """
        if self._transient or self._name in exclude_models.ignore_model:
            return False
        try:
            uid = request and request.session.uid
        except Exception:
            return False
        if not uid:
            return False
        return self.env['res.users'].sudo().browse(uid)._is_internal()

    def _advanced_session_device_log(self):
        try:
            sid = request.session.sid[:42]
        except Exception:
            sid = False
        if sid:
            device_log = self.env['res.device.log'].sudo().search([('session_identifier', '=', sid)], limit=1)
            if device_log:
                return device_log
        return self.env['res.device.log']._reza_current_device_log(self.env.uid)

    def write(self, vals):
        if not self._asm_should_log():
            return super().write(vals)
        try:
            moduel_state = self.env['ir.module.module'].sudo().search([('name','=','advanced_session_management')]).state
            if self._name not in exclude_models.ignore_model and moduel_state == 'installed':
                config_parameter_obj = self.env['ir.config_parameter'].sudo()
                field_obj = self.env['ir.model.fields'].sudo()
                for record in self:
                
                    activity_log_obj = self.env['activity.log'].sudo()

                    # login_log = record.env['login.log'].sudo().search([('session_id','=',request.session.sid)],limit=1)
                    login_log = record._advanced_session_device_log()
                    if not self._transient:
                        disable = 'False'
                        if disable == 'False':
                            value = ''
                            view_changes = []
                            for val in vals:
                                if str(record[val]) != str(vals[val]):
                                    field_name = field_obj.search([('name','=',val),('model','=',record._name)],limit=1)
                                    
                                    if field_name.ttype not in ['binary','many2many','one2many','many2one','html','text']:
                                        if not record[val] and vals[val]:
                                            value = value + """ New value <b>%s</b> was added for the field <b>%s</b>. <br/>""" % (vals[val],field_name.field_description)
                                        if not vals[val] and record[val]:
                                            value = value + """ The value is set to blank from <b>%s</b> for the <b>%s</b>. <br/>""" % (record[val],field_name.field_description)
                                        if vals[val] and record[val]:
                                            value = value + """ The value of the <b>%s</b> was updated from <b>%s</b> to <b>%s</b>. <br/>""" % (field_name.field_description,record[val],vals[val])
                                    elif field_name.ttype in ['html','binary','text']:
                                        value = value + """ <b>%s</b> is Changed. <br/>""" % (field_name.field_description)
                                        # A binary value is a base64 file (product images on ecom):
                                        # two copies per edit would bloat edit.value. Record the change only.
                                        is_binary = field_name.ttype == 'binary'
                                        view_changes.append((0,0,{
                                            'name':field_name.field_description,
                                            'old':'(file)' if is_binary else record[val],
                                            'new':'(file)' if is_binary else vals[val],
                                        }))
                                    elif field_name.ttype in ['many2one']:
                                        if record[val].id != vals[val]:
                                            obj = record.env[field_name.relation].sudo()
                                            if not record[val] and vals[val]:
                                                new_value = obj.browse(vals[val]).display_name
                                                value = value + """ New value <b>%s</b> was added for the field <b>%s</b>. <br/>""" % (new_value,field_name.field_description)
                                            if not vals[val] and record[val]:
                                                old_value = obj.browse(record[val].id).display_name
                                                value = value + """ The value is set to blank from <b>%s</b> for the <b>%s</b>. <br/>""" % (old_value,field_name.field_description)
                                            if vals[val] and record[val]:
                                                old_value = obj.browse(record[val].id).display_name
                                                new_value = obj.browse(vals[val]).display_name
                                                value = value + """ The value of the <b>%s</b> was updated from <b>%s</b> to <b>%s</b>. <br/>""" % (field_name.field_description,old_value,new_value)

                                    elif field_name.ttype in ['many2many']:
                                        obj = record.env[field_name.relation].sudo()
                                        # if record._name != 'res.users' and field_name.name in ['groups_id','']:
                                        if len(vals[val][0]) == 3:
                                            
                                            old_value = ''
                                            new_value = ''
                                            if not record[val] and vals[val][0][2]:
                                                for new_id in vals[val][0][2]:
                                                    new_value = new_value + obj.browse(new_id).display_name + '|'
                                                value = value + """ New value <b>%s</b> was added for the field <b>%s</b>. <br/>""" % (new_value,field_name.field_description)
                                            elif not vals[val][0][2] and record[val]:
                                                for new_id in record[val].ids:
                                                    old_value = old_value + obj.browse(new_id).display_name + '|'
                                                value = value + """ The value is set to blank from <b>%s</b> for the <b>%s</b>. <br/>""" % (old_value,field_name.field_description)
                                            elif vals[val][0][2] and record[val]:
                                                for new_id in vals[val][0][2]:
                                                    new_value = new_value + obj.browse(new_id).display_name + '|'
                                                for new_id in record[val].ids:
                                                    old_value = old_value + obj.browse(new_id).display_name + '|'
                                                value = value + """ The value of the <b>%s</b> was updated from <b>%s</b> to <b>%s</b>. <br/>""" % (field_name.field_description,old_value,new_value)
                                        elif len(vals[val][0]) == 2:
                                            if not request.session.temp:
                                                for m2m_rec in vals[val]:
                                                    browse_rec = obj.browse(m2m_rec[1])
                                                    categ_name = ''
                                                    if record._name == 'res.users' and field_name.name == 'group_ids':
                                                        categ_name = (browse_rec.privilege_id.name + '/') if browse_rec.privilege_id else ''
                                                    if m2m_rec[1] in record[val].ids:
                                                        value = value + """ <b>%s</b> is removed in <b>%s</b>. <br/>""" % (categ_name+browse_rec.name,field_name.field_description)
                                                    else:
                                                        value = value + """ <b>%s</b> is added in <b>%s</b>. <br/>""" % (categ_name+browse_rec.name,field_name.field_description)
                                                request.session.temp = True
                                            else:
                                                request.session.temp = False
                            if record._name in SECRET_VALUE_MODELS:
                                # Settings hold API keys, passwords and webhook
                                # secrets. Record THAT a setting changed, never
                                # its old or new value: edit.value is stored in
                                # clear text and reza_user_activity emails it out
                                # in the monthly archive.
                                view_changes = [
                                    (0, 0, dict(change[2], old=HIDDEN, new=HIDDEN))
                                    for change in view_changes
                                ]
                            if value:
                                log_name = vals.get('name') or vals.get('display_name') or record.display_name
                                activity_log_obj.create({
                                    'name':log_name,
                                    'model':record._name,
                                    'res_id':str(record.id),
                                    'action':'edit',
                                    'device_id':login_log.id or False,
                                    'user_id':login_log.user_id or request.session.uid or self.env.uid,
                                    # 'edit_value_id':edit_value.id,
                                    'value':value,
                                    'view':'n/a',
                                    'edit_value_ids':view_changes,
                                })
        except:
            pass
        return super().write(vals)

    @api.model_create_multi
    # @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        res = super().create(vals_list)
        if not res._asm_should_log():
            return res
        try:
            moduel_state = self.env['ir.module.module'].sudo().search([('name','=','advanced_session_management')]).state
            config_parameter_obj = self.env['ir.config_parameter'].sudo()
            
            for record in res:
                if record._name not in exclude_models.ignore_model and moduel_state == 'installed':
                    activity_log_obj = self.env['activity.log'].sudo()
                    # login_log = self.env['login.log'].sudo().search([('session_id','=',request.session.sid)],limit=1)
                    login_log = record._advanced_session_device_log()
                    if not self._transient:
                        disable = 'False'
                        if disable == 'False':
                            
                            activity_log_obj.create({
                                'name':record.display_name or record.name or '',
                                'model':record._name,
                                'res_id':str(record.id),
                                'action':'create',
                                'device_id':login_log.id or False,
                                'user_id':login_log.user_id or request.session.uid or self.env.uid,
                                'view':'n/a',
                            })
        except:
            pass
        return res
    
    def unlink(self):
        if not self._asm_should_log():
            return super().unlink()
        moduel_state = self.env['ir.module.module'].sudo().search([('name','=','advanced_session_management')]).state
        config_parameter_obj = self.env['ir.config_parameter'].sudo()
        
        for record in self:
            try:
                if record._name not in exclude_models.ignore_model and moduel_state == 'installed':
                    activity_log_obj = self.env['activity.log'].sudo()
                    # login_log = record.env['login.log'].sudo().search([('session_id','=',request.session.sid)],limit=1)
                    login_log = record._advanced_session_device_log()
                    if not self._transient:
                        disable = 'False'
                        if disable == 'False':
                            activity_log_obj.create({
                                'name':record.display_name,
                                'model':record._name,
                                'res_id':str(record.id),
                                'action':'delete',
                                'device_id':login_log.id or False,
                                'user_id':login_log.user_id or request.session.uid or self.env.uid,
                                'view':'n/a',
                            })
            except:
                pass
        return super().unlink()

class ir_module_module(models.Model):
    _inherit = 'ir.module.module'


    def _button_immediate_function(self, function):
        config_parameter_obj = self.env['ir.config_parameter'].sudo()
        value = config_parameter_obj.search([('key','=','disable_log')],limit=1)
        
        if value:
            value.value = 'True'
        else:
            config_parameter_obj.create({'key':'disable_log','value':'True'})
        res = super(ir_module_module, self)._button_immediate_function(function)
        for record in self:
            if record.name != 'advanced_session_management':
                # login_log = record.env['login.log'].sudo().search([('session_id','=',request.session.sid)],limit=1)
                try:
                    sid = request.session.sid[:42]
                except Exception:  # shell / cron: no request, nothing to credit
                    sid = False
                login_log = sid and self.env['res.device.log'].sudo().search([('session_identifier','=',sid)],limit=1)
                if login_log:
                    value = ''
                    if function.__name__ == 'button_install':
                        value = ' installed'
                    if function.__name__ == 'button_uninstall':
                        value = ' uninstalled'
                    if function.__name__ == 'button_upgrade':
                        value = ' upgrade'
                    if function.__name__ == 'install_or_upgrade':
                        value = ' install or upgrade'
                    
                    record.env['activity.log'].sudo().create({
                        'name':record.display_name,
                        'model':record._name,
                        'res_id':str(record.id),
                        'action':'edit',
                        'device_id':login_log.id,
                        'user_id':login_log.user_id.id,
                        # 'edit_value_id':edit_value.id,
                        'view':'n/a',
                        'value':""" <b>%s</b> app is %s. <br/>""" % (record.display_name, value)
                    })
            config_parameter_obj.search([('key','=','disable_log')],limit=1).unlink()
        return res
    
