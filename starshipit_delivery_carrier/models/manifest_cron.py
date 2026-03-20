# -*- coding: utf-8 -*-
#################################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# License URL : https://store.webkul.com/license.html/
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import api, fields, models, _
import base64
from .starshipit_delivery_carrier import StarShipItAPI
from odoo.exceptions import ValidationError, UserError
from datetime import datetime


class StarShipItManifestCorn(models.Model):
    _name = "delivery.carrier.starshipit.manifest.cron"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Booking No", required=True, default="New", readonly=1)
    date = fields.Datetime(string="Booking Date", copy=False, default=datetime.now(), readonly=1)

    @api.model
    def create(self, vals_list):
        """give Manifest number automatically"""
        if vals_list["name"] == "New":
            vals_list["name"] = self.env["ir.sequence"].next_by_code("delivery.carrier.starshipit.manifest.cron.id")
        return super().create(vals_list)

    def starshipit_manifest_cron(self):
        delivery = self.env["delivery.carrier"].search(
            [("delivery_type", "=", "starshipit")], limit=1)
        config = delivery.wk_get_carrier_settings(["starshipit_api_key", "starshipit_subscription_key"])
        sdk = StarShipItAPI(
            starshipit_api_key=config["starshipit_api_key"],
            starshipit_subscription_key=config["starshipit_subscription_key"],
        )
        header = sdk.get_starshipit_header()
        unmanifested = sdk.request("GET", "/api/orders/shipments?status=unmanifested", {}, header)
        # unmanifested = {'status': 'unmanifested', 'orders': [{'order_id': 542046046, 'order_number': '10001', 'date': '2025-04-02T12:27:04.0562624', 'name': 'John Smith', 'carrier_name': 'Plain Label', 'carrier_service_code': 'Plain Label', 'tracking_numbers': [''], 'country': 'Australia'}, {'order_id': 542047332, 'order_number': '10001', 'date': '2025-04-02T12:27:04.0406415', 'name': 'John Smith', 'carrier_name': 'Plain Label', 'carrier_service_code': 'Plain Label', 'tracking_numbers': [''], 'country': 'Australia'}], 'total_pages': 1, 'success': True}
        if unmanifested["orders"]:
            order_ids = [order["order_id"] for order in unmanifested["orders"]]
            # manifested = sdk.request('POST','/api/manifests/carrier',{"carrier": "PlainLabel"},header) # not need when we get manifest label it goes manifest automatically
            label = sdk.request("POST", "/api/orders/manifest", {"order_ids": order_ids}, header)
            # label = {'label_type': 'ManifestReport', 'pdf': 'JVBERi0xLjQKJeLjz9MKMyAwIG9iago8PC9MZW5ndGggMTI0MC9GaWx0ZXIvRmxhdGVEZWNvZGU+PnN0cmVhbQp4nKWYXW/bNhSG7/UrCOxiG5ByFEXqo3f52AJ0a5bOLno5yLEaq7XkVpZbZL9+RxI/DiWaCbYCdXQonvchD/nSkhmJyauYMCILCZ8PTfQ1ulpHU7zewgUb/vzyW0xiTtYfo5/Iz+tPuplBbo66QSyEc+PliXHO/2OmzP5X4q/r6B3MevjPyRtov4VrqMFQFQbliQvKYyIFJDcgzkksRvH7fVm35I9yU+3J27KtP1bHnvxVfTl0/YAF2YAoZ0RkVnEa7tXpWLfV8UjuyqZ6rURwUpHRPLWJZp7fq83n096TABTJZ5Tr07E/NFX345Fcbrcd8AIonW1Q7+8vyGpX7r6cOnJVNruqLy/I7a78py435fYCkDFj/IK8v/cPh6ez4ZjSXXdV2VdbcgOfgRFpATOiD9UWirYtny7I5Zeu3hM+jIJLP5+xc/y7U7OpugBZpxpy4UUkmZgh1oe+3JP78uFz+VgFqm0yDYH7CWK+cybC9aE91o9tU7V9iCLm2+cMhc93zkT5UNWPuz6gz+d7JqYJ81riK3wOV59A4/vYwmPKJOFZTiVpopxTmatoH62Gu3K4W8A9dZ2y8c47jxbOHvpntJBILE8oy5WYug6IOelNlMSMcuEMLafCjm0KAnqOQBMJBoPFesP9TCg9HQT0HAHQy3Oa4tIJBlPUejoI6WGBJpI5o4Wjlxc01uXTQUDPEWiiVAoKB77Vk3lMhdbTQUDPEWiiLE5pglc3lZImXOnpIKDnCIBeBnsZz3e4n+v11UFIDwsMO5nNdh80mP2iA6WXQa9E10IHwb05mkYW2DRjhEwD+cY0In7ONEpL73ojZo1iTBMQc9KtadDQjE+saQJ6joA1jdFDPrGmCeg5AtY0Rg/5xJompIcFrGmsnvWJNU1AzxGwpjF6yCfWNAE9R8Caxughn1jTBPQcAWsao4d8Yk0T0sMC1jR291mfWNMoPeQTa5rg3hxNIxg2zRhNpDHmXNlg7DtGyFKgbiwFX3rPWEqRtCcMSjcoFiYjx40sdR1gOerWcQamG8zEEBs7Uk1tCgI8B2AdaXi6QfEcPHbsyNNBgOcArGMtTzUonoPHjh55OgjxMMA62vB0g+ZhPHb8xFNBgOcArOMNTzconoPHJ8LI00GA5wDsiWB4ukHxHDw+MUaeDgI8B2BPDMtTDYrn4PGJMvJ0EOJhgD1RkM8ZNp+DxyfOZD8VKB46ZOyJY8bivO4lUDZ4QE6lfqIuxgfjP7ttR+4Oy0fpmAsKLzqLhHUHLxF1++hN4oLTRCyTbqp9/a3qyNqTkySwJT0514dT23dPywTBi+Ehf5GwOm1O3WbZX3JYwcQDqHuPuixSWiw73x+O/fVhWy0T0hS+GzLPcKruW/3gSciEoKlnKX7wdC04TT1T/f3WU0fY+bAA5t106gmvwix+5XsTFfCtUSwT3hx2LVk1db/zLVVOc0/OJbzPd+W+Lj2LlTCaLjNWT/DG7Kl+yjIvgcM0fKVPJuvPeqPfRc6Xf1EpX/nZWP55V2j1VHRaAJ75FiA9vwDzhJcswDzn+QWYZzy3APP+4QWY937RAiwqdX4B5l3RAgR+4ZLw1AajizM+m3vVbscfn1b1Y1v2p656Tf4O/PMcEkpZJq7y+Z6JcHvedMOB6I6BvGQU/wLp9moVCmVuZHN0cmVhbQplbmRvYmoKNSAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDU5NSA4NDJdL1Jlc291cmNlczw8L0ZvbnQ8PC9GMSAxIDAgUi9GMiAyIDAgUj4+Pj4vUm90YXRlIDkwL0NvbnRlbnRzIDMgMCBSL1BhcmVudCA0IDAgUj4+CmVuZG9iagoxIDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKMiAwIG9iago8PC9UeXBlL0ZvbnQvU3VidHlwZS9UeXBlMS9CYXNlRm9udC9IZWx2ZXRpY2EtQm9sZC9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKNCAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s1IDAgUl0+PgplbmRvYmoKNiAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgNCAwIFI+PgplbmRvYmoKNyAwIG9iago8PC9Qcm9kdWNlcihpVGV4dFNoYXJwkiA1LjUuMSCpMjAwMC0yMDE0IGlUZXh0IEdyb3VwIE5WIFwoQUdQTC12ZXJzaW9uXCkpL0NyZWF0aW9uRGF0ZShEOjIwMjUwNDAyMTMwMTE4KzAwJzAwJykvTW9kRGF0ZShEOjIwMjUwNDAyMTMwMTE4KzAwJzAwJyk+PgplbmRvYmoKeHJlZgowIDgKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAxNDU0IDAwMDAwIG4gCjAwMDAwMDE1NDIgMDAwMDAgbiAKMDAwMDAwMDAxNSAwMDAwMCBuIAowMDAwMDAxNjM1IDAwMDAwIG4gCjAwMDAwMDEzMjMgMDAwMDAgbiAKMDAwMDAwMTY4NiAwMDAwMCBuIAowMDAwMDAxNzMxIDAwMDAwIG4gCnRyYWlsZXIKPDwvU2l6ZSA4L1Jvb3QgNiAwIFIvSW5mbyA3IDAgUi9JRCBbPGVhMjhjNThjOGE3YzAzN2UzNzBiODUzZTYzNTU2MmY2PjxlYTI4YzU4YzhhN2MwMzdlMzcwYjg1M2U2MzU1NjJmNj5dPj4KJWlUZXh0LTUuNS4xCnN0YXJ0eHJlZgoxODkzCiUlRU9GCg==', 'success': True}
            crt_mnfst = self.create({"name": "New"})
            attachment = {
                "name": f"Manifest label {self.name}.pdf",
                "datas": label["pdf"],
                "res_model": "delivery.carrier.starshipit.manifest.cron",
                "res_id": crt_mnfst.id,
            }
            attachment_id = self.env["ir.attachment"].create(attachment)
            crt_mnfst.message_post(
                body="Please find the attached PDF document.",
                attachment_ids=[attachment_id.id],
            )
        else:
            pass