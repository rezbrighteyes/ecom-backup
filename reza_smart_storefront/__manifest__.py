{
    'name': 'Smart Storefront',
    'version': '18.0.2.0.0',
    'category': 'Website/eCommerce',
    'summary': 'Trust badges, delivery estimates, stock urgency, smart cross-sells',
    'author': 'Reza D Shiraz',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'stock'],
    'data': [
        'views/product_page.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'reza_smart_storefront/static/src/css/storefront.css',
            'reza_smart_storefront/static/src/js/cross_sell_cart.js',
        ],
    },
    'installable': True,
    'autoinstall': False,
    'application': False,
}
