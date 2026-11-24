{
    'name': 'Reza Ecom Core',
    'version': '20.0.1.0.1',
    'category': 'Website/eCommerce',
    'summary': 'Core eCommerce utilities and enhancements',
    'author': 'Reza D Shiraz',
    'license': 'LGPL-3',
    'depends': [
        'website_sale',
        'loyalty',
        # action_generate_coupon overrides d3_sale_cart's and reads its website fields
        'd3_sale_cart',
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
