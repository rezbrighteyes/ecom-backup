{
    'name': 'Reza Smart Storefront',
    'version': '18.0.1.0.0',
    'summary': 'Smart storefront features for non-SS websites',
    'author': 'reza',
    'category': 'Website/Website',
    'license': 'OPL-1',
    'depends': ['website_sale', 'stock'],
    'data': [
        'views/product_page.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'post_update_hook': 'post_update_hook',
    'installable': True,
    'auto_install': False,
}
