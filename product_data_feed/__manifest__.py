# Copyright © 2020 Garazd Creation (https://garazd.biz)
# @author: Yurii Razumovskyi (support@garazd.biz)
# @author: Iryna Razumovska (support@garazd.biz)
# License OPL-1 (https://www.odoo.com/documentation/master/legal/licenses.html#odoo-apps).

{
    'name': 'Product Data Feed',
    'version': '18.0.1.1.6',
    'category': 'Hidden',
    'author': 'Garazd Creation',
    'website': 'https://garazd.biz/shop',
    'license': 'OPL-1',
    'summary': 'Product Data Feed | Data Feed Manager',
    'images': ['static/description/banner.png', 'static/description/icon.png'],
    'live_test_url': 'https://garazd.biz/r/dTG',
    'depends': [
        'website_sale_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/product_data_feed_recipient_data.xml',
        'data/ir_filters_data.xml',
        'views/product_data_feed_views.xml',
        'views/product_data_feed_column_views.xml',
        'views/product_data_feed_column_value_views.xml',
        'views/product_data_feed_recipient_views.xml',
        'views/product_template_views.xml',
        'views/product_product_views.xml',
    ],
    'demo': [
        'demo/product_pricelist_demo.xml',
    ],
    'price': 10.00,
    'currency': 'EUR',
    # ---------------------------
    # LIMITATIONS ON SALE AND USE
    # ---------------------------
    # This module is not sold or distributed separately.
    # It can only be delivered as part of Odoo solutions by Garazd Creation.
    # Prohibited to use this module separately from the solution with which it is supplied.
    # Contact us if you want to use the module for other purposes.
    'support': 'support@garazd.biz',
    'application': True,
    'installable': True,
    'auto_install': False,
}
