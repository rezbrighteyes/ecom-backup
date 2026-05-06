{
    'name': 'Reza Product Reviews',
    'version': '18.0.1.0.0',
    'category': 'Website/eCommerce',
    'summary': 'Product review management with moderation, notifications and post-purchase requests',
    'author': 'Reza D Shiraz',
    'license': 'LGPL-3',
    'depends': [
        'website_sale',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_template.xml',
        'views/review_views.xml',
        'views/review_template.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}