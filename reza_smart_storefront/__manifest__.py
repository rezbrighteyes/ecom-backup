{
    'name': 'Reza Smart Storefront',
    'version': '18.0.2.0.1',
    'summary': 'Smart storefront features for non-SS websites',
    'author': 'reza',
    'category': 'Website/Website',
    'license': 'OPL-1',
    'depends': ['website_sale', 'stock', 'd3_website_product_extended', 'RezaDs_seo_auto'],
    'data': [
        'views/product_page.xml',
        'views/drift_kart_banner.xml',
        'views/drift_kart_landing.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'reza_smart_storefront/static/src/css/storefront.css',
            'reza_smart_storefront/static/src/css/drift_banner.css',
            'reza_smart_storefront/static/src/css/drift_landing.css',
            'reza_smart_storefront/static/src/css/sale_badge.css',
            'reza_smart_storefront/static/src/js/cross_sell_cart.js',
            'reza_smart_storefront/static/src/js/drift_banner_position.js',
            'reza_smart_storefront/static/src/js/drift_landing.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'post_update_hook': 'post_update_hook',
    'installable': True,
    'auto_install': False,
}
