{
    'name': 'Reza Product Reviews',
    'version': '18.0.1.3.0',
    'category': 'Website/eCommerce',
    'summary': 'Product review management with moderation, notifications and post-purchase requests',
    'author': 'Reza D Shiraz',
    'license': 'LGPL-3',
    'depends': [
        'website_sale',
        'mail',
        'portal_rating',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/review_channel.xml',
        'data/mail_template.xml',
        'data/cron.xml',
        'views/review_views.xml',
        'views/review_template.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'reza_product_reviews/static/src/js/review_frontend.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}