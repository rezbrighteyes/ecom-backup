{
    'name': 'Smart SEO by Reza D Shiraz',
    'version': '20.0.11.1.0',
    'category': 'Website/eCommerce',
    'summary': 'Complete eCommerce SEO: Schema.org, breadcrumbs, auto meta, 301 redirects, sitemap, dashboard',
    'author': 'Reza D Shiraz',
    'license': 'LGPL-3',
    # website_ids on product.template belongs to sh_product_multi_website, and this
    # module reads it in the SEO tab view and in the constraint on product.website.seo.
    # Undeclared, whether the field exists when this module's views are validated is
    # decided by module load order rather than by anything stated.
    'depends': ['website_sale', 'stock', 'sh_product_multi_website'],
    'data': [
        'views/pagination_seo.xml',
        'views/product_schema.xml',
        'views/site_schema.xml',
        'views/seo_health_views.xml',
        'views/product_seo_tab.xml',
        'views/product_page_website_body.xml',
        'views/product_website_seo_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/seo_wizard_views.xml',
        'security/ir.access.csv',
    ],
    'installable': True,
    'autoinstall': False,
    'application': False,
}
