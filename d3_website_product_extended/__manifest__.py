{
    'name': 'D3 Website Product Extended',
    'summary': "D3 Website Product Extended",
    'description': """
        D3 Website Product Extended
    """,
    'author': "Dimension3 Technology",
    'website': "https://d-3system.com.au",
    'category': 'Website/Website',
    'version': '18.1',
    'depends': ['base', 'product', 'website_sale'],
    'data': [
        'views/templates.xml',
        'views/product_views.xml'
    ],
    'assets': {
        'web.assets_frontend': [
            'd3_website_product_extended/static/src/scss/website_variants_grid.scss',
            'd3_website_product_extended/static/src/js/website_sale.js',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}