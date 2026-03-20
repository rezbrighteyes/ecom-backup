{
    'name': 'Smart SEO by Reza D Shiraz',
    'version': '18.0.8.0.0',
    'category': 'Website/eCommerce',
    'summary': 'Complete eCommerce SEO: Schema.org, breadcrumbs, auto meta, 301 redirects, sitemap, dashboard',
    'author': 'Reza D Shiraz',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_schema.xml',
        'views/seo_health_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/seo_wizard_views.xml',
    ],
    'installable': True,
    'autoinstall': False,
    'application': False,
}
