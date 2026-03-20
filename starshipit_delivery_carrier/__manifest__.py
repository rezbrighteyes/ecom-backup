# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################
{
    "name":  "Starshipit Shipping Integration",
    "summary":  """Odoo Starshipit Shipping Integration""",
    "category":  "Website/Shipping Logistics",
    "version":  "1.0.0",
    "author":  "Webkul Software Pvt. Ltd.",
    "license":  "Other proprietary",
    "website":  "https://store.webkul.com",
    "description":  """ Odoo Starshipit Shipping Integration OAuth module allows you to create shipments and choose carrier options 
    for smooth shipping management and delivery services.""",
    "live_test_url":  "https://odoodemo.webkul.in?module=starshipit_delivery_carrier",
    "depends":  ['mail','odoo_shipping_service_apps'],
    "data":  [
        'security/ir.model.access.csv',
        'data/delivery_demo.xml',
        'data/manifest_cron.xml',
        'views/starshipit_delivery_carrier.xml',
        'wizard/choose_delivery_carrier.xml',
        'wizard/starshipit_services.xml',
    ],
    "images":  ['static/description/Banner.png'],
    "application":  True,
    "installable":  True,
    "price":  149,
    "currency":  "USD",
    "pre_init_hook":  "pre_init_check",
}
