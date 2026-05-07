from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_d3_credit_control = fields.Boolean()
    module_d3_customer_statement = fields.Boolean()
    module_d3_mrp_cost = fields.Boolean()
    module_d3_partner_statement = fields.Boolean()
    module_d3_product_image = fields.Boolean()
    module_d3_reporting = fields.Boolean()
    module_d3_website_price = fields.Boolean()
    module_d3_website_quotation = fields.Boolean()
    module_d3_wesbite_rebranding = fields.Boolean() 
    module_date_range = fields.Boolean()
    module_helpdesk_user = fields.Boolean() 
    module_partner_contact_access_link = fields.Boolean()
    module_odoo_quote_sale_revision_number = fields.Boolean()
    module_ondao_flexible_chatter = fields.Boolean() 
    module_partner_statement = fields.Boolean()
    module_pragmatic_odoo_xero_connector = fields.Boolean()
    module_product_image_import = fields.Boolean()
    module_project_user = fields.Boolean()
    module_report_xlsx = fields.Boolean()
    module_report_xlsx_helper = fields.Boolean()
    module_sale_order_line_sequence = fields.Boolean()
    module_salesperson_stop_follower = fields.Boolean()
    module_setu_cash_flow_forecasting = fields.Boolean()
    module_timesheet_user = fields.Boolean()
    module_web_remember_tree_column_width = fields.Boolean()
    module_website_ask_login = fields.Boolean()
    module_website_sale_hide_price = fields.Boolean()
    

