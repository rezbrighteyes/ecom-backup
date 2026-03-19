{
    'name': 'D3 Website Product Extended',
    'summary': """
Extends Odoo Website Shop behavior by enhancing product variant visibility, modifying the shop controller, and improving product grid rendering with variant‑based displays and UI customizations.
    """,
    'description': """
This module enhances Odoo’s eCommerce product browsing experience. It extends the website product grid, adds dynamic variant rendering, and overrides key parts of the /shop controller to provide richer filtering, pricing, and product listing behavior. It also introduces new front‑end assets, custom templates, and configuration settings for managing how products and variants appear on the website.
    """,
    'author': "Dimension3 Technology",
    'website': "https://d-3system.com.au",
    'category': 'Website/Website',
    'version': '18.6',
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
    'license': 'OPL-1',
}