# Copyright © 2021 Garazd Creation (https://garazd.biz)
# @author: Yurii Razumovskyi (support@garazd.biz)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

{
    'name': 'Importing from URL',
    'version': '20.0.1.2.0',
    'category': 'Hidden',
    'author': 'Garazd Creation',
    'website': 'https://garazd.biz/shop',
    'license': 'LGPL-3',
    'summary': 'Helper to Import from URLs. Technical module to import data from URLs.',
    'depends': [
        'base',
    ],
    'data': [
        'wizard/base_import_helper_views.xml',
        'security/ir.access.csv',
    ],
    'support': 'support@garazd.biz',
    'application': False,
    'installable': True,
    'auto_install': False,
}
