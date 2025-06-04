{
    'name': 'D3 Website Product Extended',
    'summary': "D3 Website Product Extended",
    'description': """
        D3 Website Product Extended
    """,
    'author': "Dimension3 Technology",
    'website': "https://d-3system.com.au",
    'category': 'Website/Website',
    'version': '18.4',
    'depends': ['base', 'product', 'website_sale', 'website_sale_stock'],
    'data': [
        'views/templates.xml',
        'views/product_views.xml',
        'views/res_config_settings.xml'
    ],
    'assets': {
        'web.assets_frontend': [
            'd3_website_product_extended/static/src/scss/website_variants_grid.scss',
            'd3_website_product_extended/static/src/js/website_sale.js',
            'd3_website_product_extended/static/src/xml/website_sale.xml'
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}