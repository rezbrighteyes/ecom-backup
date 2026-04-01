{
    'name': 'Sunglass Superstore — Product Page',
    'version': '18.0.2.0.0',
    'summary': 'Custom product page design for Sunglass Superstore (self-contained)',
    'author': 'reza',
    'category': 'Website/Website',
    'license': 'OPL-1',
    'depends': [
        'website_sale',
        'website_sale_wishlist',
        'stock',
    ],
    'data': [
        'views/templates.xml',
        'views/sf_product_page.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'sunglass_superstore_product_page/static/src/scss/product_page.scss',
            'sunglass_superstore_product_page/static/src/css/storefront.css',
            'sunglass_superstore_product_page/static/src/js/cross_sell_cart.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'post_update_hook': 'post_update_hook',
    'installable': True,
    'auto_install': False,
}
