{
    'name': 'Sunglass Superstore — Product Page',
    'version': '18.0.1.0.0',
    'summary': 'Custom product page design for Sunglass Superstore',
    'author': 'reza',
    'category': 'Website/Website',
    'license': 'OPL-1',
    'depends': [
        'website_sale',
        'website_sale_wishlist',
    ],
    'data': [
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'sunglass_superstore_product_page/static/src/scss/product_page.scss',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
}
