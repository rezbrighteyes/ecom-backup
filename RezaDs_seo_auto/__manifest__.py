{
    'name': 'RezaDs SEO Auto',
    'version': '18.0.6.0.0',
    'category': 'Website/eCommerce',
    'summary': 'Auto SEO, Schema.org, 301 redirects, image alt text, SEO health dashboard, bulk wizard',
    'author': 'Reza D Shiraz',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_schema.xml',
        'views/seo_health_views.xml',
        'wizard/seo_wizard_views.xml',
    ],
    'installable': True,
    'autoinstall': False,
    'application': False,
}
