{
    'name': 'Reza Ecom Core',
    'version': '20.0.1.0.0',
    'category': 'Website/eCommerce',
    'summary': 'Core eCommerce utilities and enhancements',
    'author': 'Reza D Shiraz',
    'license': 'LGPL-3',
    'depends': [
        'website_sale',
        'loyalty',
    ],
    'data': [
        'views/product_template_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'reza_ecom_core/static/src/js/product_image_preview.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
