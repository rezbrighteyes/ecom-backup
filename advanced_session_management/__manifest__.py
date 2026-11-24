# -*- coding: utf-8 -*-
#################################################################################
# Author      : Terabits Technolab (<www.terabits.xyz>)
# Copyright(c): 2021-25
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################
{
    'name': 'Advanced User Audit | User Activity Audit | Login Notification',
    'summary': """Monitor and manage user sessions in Odoo with login tracking, active session control, session history, login notifications, IP tracking, device information, and user activity monitoring. Improve account security and gain better visibility into user activity.
session management, user session tracking, login history, user activity monitoring, login notifications, IP tracking, session audit""",
    'version': '20.0.1.2.1',
    'sequence': 6,
    'author': 'Terabits Technolab',
    'license': 'OPL-1',
    'category': 'Services',
    'website': 'https://www.terabits.xyz/apps/19.0/advanced_session_management',
    'description': """Monitor and manage user sessions in Odoo with login tracking, active session control, session history, login notifications, IP tracking, device information, and user activity monitoring. Improve account security and gain better visibility into user activity.""", 
    "price": "199.99",
    "currency": "USD",
    'depends':['mail','http_routing'],
    'data':[
        # Groups first: the access file names them, and a fresh install
        # (no groups yet) hangs on the forward reference otherwise.
        'security/res_groups.xml',
        'data/cron.xml',
        'data/upgrade_cron_settings.xml',
        'data/email_template.xml',
        'views/res_config_settings_view.xml',
        'views/login_log_view.xml',
        'views/res_device_views.xml',
        'views/activity_log_view.xml',
        'views/res_user_view.xml',
        'security/ir.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_session_management/static/src/scss/style.scss',
            'advanced_session_management/static/src/js/router_service.js',
        ],
    },
    'external_dependencies': {
        'python': ['user_agents']
    },
    'application': True,
    'installable': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'live_test_url': 'https://www.terabits.xyz/request_demo?source=index&version=16&app=advanced_session_management',
    'images': ['static/description/banner.gif'],
}
