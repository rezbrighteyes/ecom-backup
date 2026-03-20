# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo.exceptions import ValidationError, UserError
from odoo.addons.odoo_shipping_service_apps.tools import ensure_str
from odoo import api, fields, models
import requests
import json
import base64
import ast


class StarShipItAPI:
    
    def __init__(self, *args, **kwargs):
        self.starshipit_api_key = kwargs.get('starshipit_api_key')
        self.starshipit_subscription_key = kwargs.get('starshipit_subscription_key')
        self.APIEND = "https://api.starshipit.com"
    def get_starshipit_header(self):
        headers = {
            'Content-Type': 'application/json',
            'StarShipIT-Api-Key': self.starshipit_api_key,
            'Ocp-Apim-Subscription-Key': self.starshipit_subscription_key
            }
        return headers
    
    def request(self,method, url, payload, headers):
        url = self.APIEND + url
        payload = json.dumps(payload)
        response = requests.request(method, url, headers=headers, data=payload)
        return response.json()

class StarshipitDeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"
    
    def get_starshipit_packages(self, order=None, pickings=None, currency_code=None, order_no=False, return_order=False):
        result = dict()
        packages = []
        if order:
            def calc_total_weight():
                total_weight = 0.0
                for order_line in order.order_line:
                    total_weight += order_line.product_id.weight * order_line.product_uom_qty
                return total_weight
            package_id = self.packaging_id
            package_data = dict(
                    weight=calc_total_weight(),
                    height=package_id.package_type_id.height * (0.001), # use for converting mm to m
                    width=package_id.package_type_id.width * (0.001),
                    length=package_id.package_type_id.packaging_length * (0.001)
            )
            packages.append(package_data)
        else:
            for each in pickings.move_line_ids.result_package_id:
                package_data = dict(
                        weight=round(each.shipping_weight,2),
                        height=each.height,
                        width=each.width,
                        length=each.length,
                    )
                if (order_no == True):
                    package_data = dict(
                        order_number = each.id if not return_order else 'R-'+str(each.id),
                        package = package_data
                    )
                    packages.append(package_data)
                else:
                    packages.append(package_data)
        return packages
    
    def get_starshipit_address(self, address):
        starshipit_address = dict(
            name=address.get('name'), 
            email=address.get('email'),
            phone=address.get('phone'), 
            street=address.get('street', ''), 
            city=address.get('city'), 
            state=address.get('state_code'),
            country=address.get('country_name'),
            post_code=address.get('zip'),
            country_code=address.get('country_code')
        )
        return starshipit_address
    
    def _get_recipient_and_shipper(self, order, picking):
        if order:
            recipient = order.partner_shipping_id or order.partner_id
            shipper = order.warehouse_id.partner_id
        else:
            recipient = picking.partner_id
            shipper = picking.picking_type_id.warehouse_id.partner_id
        return recipient, shipper
    
    def _get_starshipit_rate_data(self, order=False, picking=False):
        receiver,shipper = self._get_recipient_and_shipper(order,picking)
        self.wk_validate_object_fields(shipper, ['city', 'zip', 'country_id'])
        self.wk_validate_object_fields(receiver, ['city', 'zip', 'country_id'])
        shipper_address = self.get_shipment_shipper_address(order=order,picking=picking)
        receiver_address = self.get_shipment_recipient_address(order=order,picking=picking)
        currency_id = self.get_shipment_currency_id(order)
        currency_code = currency_id.name
        pack=self.get_starshipit_packages(order=order,pickings=picking, currency_code=currency_code)
        
        starshipit_rate_request=dict(
                destination=self.get_starshipit_address(receiver_address),
                sender=self.get_starshipit_address(shipper_address),
                packages=pack
            )
        return starshipit_rate_request

    def starshipit_get_shipping_price(self, order=False, picking=False):
        if picking and not picking.has_packages:
            raise ValidationError("Create package first then click on get Starshipit rates!")
        result = {}
        config = self.wk_get_carrier_settings(['starshipit_api_key', 'starshipit_subscription_key'])
        sdk = StarShipItAPI(
            starshipit_api_key = config['starshipit_api_key'],
            starshipit_subscription_key = config['starshipit_subscription_key']
        )
        currency_id = self.get_shipment_currency_id(order)
        starshipit_rate_request = self._get_starshipit_rate_data(order,picking)
        header = sdk.get_starshipit_header()
        response = sdk.request('POST','/api/rates',starshipit_rate_request,header)
        
        """ # response for test 
        response = {
                "rates": [
                    {
                    "service_name": "PARCEL POST + SIGNATURE",
                    "service_code": "7B05",
                    "total_price": 12.05
                    },
                    {
                    "service_name": "Express Shipping",
                    "service_code": "Plain Label",
                    "total_price": 14.65
                    }
                ],
                "success": 'true'
                } """
        rates = response["rates"]
        return rates

    
    @api.model
    def starshipit_rate_shipment(self, order):
        return {
            'success' : True,
            'error_message' : False,
            'price' : order.starshipit_service_price,
            'warning_message' : None,
        }
    
    def _get_starshipit_shipment_data(self,pickings, return_order=False):
        shipper = pickings.picking_type_id.warehouse_id.partner_id
        self.wk_validate_object_fields(shipper, ['name', 'street','phone','city', 'zip', 'country_id'])
        shipper_address = self.get_shipment_shipper_address(picking=pickings)
        receiver = pickings.partner_id
        self.wk_validate_object_fields(receiver, ['name', 'street', 'phone', 'city', 'zip', 'country_id'])
        receiver_address = self.get_shipment_recipient_address(picking=pickings)

        payload=[]
        for package in self.get_starshipit_packages(pickings=pickings,order_no=True,return_order=return_order):
            data = {
                "reference": "Online Order",
                "shipping_method": pickings.starshipit_service_name,
                "sender":self.get_starshipit_address(shipper_address),
                "destination":self.get_starshipit_address(receiver_address),
            }
            if return_order:
                data['return_order'] = True
            data.update(package)
            payload.append(data)
        payload = dict(
            orders = payload
        )
        return payload

    def starshipit_create_shipments(self, pickings,return_order=False):
        config = self.wk_get_carrier_settings(['starshipit_api_key', 'starshipit_subscription_key'])
        sdk = StarShipItAPI(
            starshipit_api_key = config['starshipit_api_key'],
            starshipit_subscription_key = config['starshipit_subscription_key']
        )
        if not pickings.starshipit_service_price:
            raise ValidationError('Kindly get the Starshipit rate first!')
        starshipit_ship_data = self._get_starshipit_shipment_data(pickings,return_order)
        header = sdk.get_starshipit_header()
        response = sdk.request('POST','/api/orders/import',starshipit_ship_data,header)
        
        order_ids = []
        # track_number = []

        # response for test
        # response = {'orders': [{'order_id': 541694213, 'order_date': '2025-04-01T10:19:57.2784764', 'order_number': '28', 'reference': 'Online Order', 'carrier': -1, 'carrier_name': '', 'carrier_service_code': '', 'shipping_method': 'PARCEL POST + SIGNATURE', 'signature_required': False, 'dangerous_goods': False, 'currency': 'USD', 'sender_details': {'name': 'Amit', 'email': 'amitchauhanwebkul@gmail.com', 'phone': '+919027504683', 'building': 'g-707', 'company': 'webkul', 'street': 'City Apartment Road', 'suburb': 'Shahpur Bamheta', 'city': 'Ghaziabad', 'state': 'UP', 'post_code': '201002', 'country': 'INDIA', 'tax_numbers': []}, 'destination': {'name': 'Deco Addict', 'email': 'deco_addict@yourcompany.example.com', 'phone': '(603)-996-3829', 'building': '', 'street': '77 Santa Barbara Rd', 'city': 'Pleasant Hill', 'state': 'CA', 'post_code': '94523', 'country': 'United States', 'delivery_instructions': '', 'tax_numbers': []}, 'packages': [{'package_id': 682298285, 'name': 'Package', 'weight': 2.0, 'height': 0.01, 'width': 0.05, 'length': 0.1, 'packaging_type': '', 'carrier_service_code': '', 'carrier_service_name': '', 'tracking_url': '', 'shipment_type': 'Outgoing'}], 'customs': {}, 'metadatas': [{'metafield_key': 'ADDRESSVALIDATED', 'value': 'True', 'required': False}, {'metafield_key': 'SOURCE', 'value': 'API', 'required': False}], 'events': [{'time': '2025-04-01T10:19:57.8566009', 'category': 'JSON', 'method': 'Imported from API', 'description': '{"Id":0,"AccountId":0,"Selected":false,"SequenceNumber":0,"SourceKey":null,"SequenceLong":0,"SequenceGuid":"00000000-0000-0000-0000-000000000000","SequenceStr":"28","OrginalSeqNumber":0,"AccountingAppId":0,"Date":"2025-04-01T10:19:57.2784764Z","ShipmentDate":"0001-01-01T00:00:00","To":"Deco Addict","CompanyName":null,"OurRef":"28","TheirRef":"Online Order","InvoiceId":null,"ConsigneeCode":null,"Email":"deco_addict@yourcompany.example.com","Telephone":"(603)-996-3829","AddressString":null,"ItemsString":null,"TrackingNumber":null,"CarrierCode":0,"CarrierName":null,"ProductName":null,"ErrorMessage":null,"Status":0,"TrackingCode":null,"Invoiced":false,"OrderValue":0.0,"OrderCurrency":null,"TaxAmount":null,"ShippingAmount":null,"PlatformShippingAmount":null,"DiscountAmount":null,"SubTotal":null,"GrandTotal":null,"TotalPaid":null,"Manifested":false,"AddressChecked":false,"AddressValidated":false,"AddressCourierValidated":false,"ReturnJob":false,"DangerousGoods":false,"DangerousGoodsTypes":[],"Items":[],"TotalItemPrice":0.0,"Boxes":[],"AddressDetails":{"Building":null,"Company":null,"Street":"77 Santa Barbara Rd","City":"Pleasant Hill","Suburb":null,"Region":null,"State":"CA","PostCode":"94523","Country":"United States","CountryId":null,"Instructions":null,"TaxList":[]},"SenderDetails":null,"BillingAddress":null,"LastUpdatedatSource":"0001-01-01T00:00:00","IntegrationId":0,"ShippingMethod":"PARCEL POST + SIGNATURE","ShippingDescription":null,"PaymentMethod":null,"PaymentDescription":null,"StoreId":null,"StoreName":null,"DTP":null,"SignatureRequired":false,"ATL":false,"PackagingType":null,"ProductCode":null,"Contents":null,"Customs":{"Incoterm":0,"ExportReason":0,"documents":null,"InvoiceRemarks":null,"InvoiceText":null,"DutyAccountNumber":null},"Tags":[],"Version":null,"DutiesAmount":0.0,"IncludesFreight":false,"IncludesCustomsClearance":false,"Note":null,"DespatchPackageId":null}'}], 'declared_value': 0.0, 'archived': False, 'manifest_number': 0, 'writeback_status': '', 'address_validation': 'Valid', 'create_return': False, 'dtp': False, 'export_type': '', 'add_insurance': False, 'insurance_value': 0.0, 'plt': False, 'type': 'Outgoing', 'platform': 'API', 'status': 'Unshipped', 'manifested': False, 'has_commercial_invoice': False, 'is_fully_packed': False}, {'order_id': 541694217, 'order_date': '2025-04-01T10:19:57.2784764', 'order_number': '30', 'reference': 'Online Order', 'carrier': -1, 'carrier_name': '', 'carrier_service_code': '', 'shipping_method': 'PARCEL POST + SIGNATURE', 'signature_required': False, 'dangerous_goods': False, 'currency': 'USD', 'sender_details': {'name': 'Amit', 'email': 'amitchauhanwebkul@gmail.com', 'phone': '+919027504683', 'building': 'g-707', 'company': 'webkul', 'street': 'City Apartment Road', 'suburb': 'Shahpur Bamheta', 'city': 'Ghaziabad', 'state': 'UP', 'post_code': '201002', 'country': 'INDIA', 'tax_numbers': []}, 'destination': {'name': 'Deco Addict', 'email': 'deco_addict@yourcompany.example.com', 'phone': '(603)-996-3829', 'building': '', 'street': '77 Santa Barbara Rd', 'city': 'Pleasant Hill', 'state': 'CA', 'post_code': '94523', 'country': 'United States', 'delivery_instructions': '', 'tax_numbers': []}, 'packages': [{'package_id': 682298289, 'name': 'Package', 'weight': 2.0, 'height': 0.01, 'width': 0.05, 'length': 0.1, 'packaging_type': '', 'carrier_service_code': '', 'carrier_service_name': '', 'tracking_url': '', 'shipment_type': 'Outgoing'}], 'customs': {}, 'metadatas': [{'metafield_key': 'ADDRESSVALIDATED', 'value': 'True', 'required': False}, {'metafield_key': 'SOURCE', 'value': 'API', 'required': False}], 'events': [{'time': '2025-04-01T10:19:58.4503526', 'category': 'JSON', 'method': 'Imported from API', 'description': '{"Id":0,"AccountId":0,"Selected":false,"SequenceNumber":0,"SourceKey":null,"SequenceLong":0,"SequenceGuid":"00000000-0000-0000-0000-000000000000","SequenceStr":"30","OrginalSeqNumber":0,"AccountingAppId":0,"Date":"2025-04-01T10:19:57.2784764Z","ShipmentDate":"0001-01-01T00:00:00","To":"Deco Addict","CompanyName":null,"OurRef":"30","TheirRef":"Online Order","InvoiceId":null,"ConsigneeCode":null,"Email":"deco_addict@yourcompany.example.com","Telephone":"(603)-996-3829","AddressString":null,"ItemsString":null,"TrackingNumber":null,"CarrierCode":0,"CarrierName":null,"ProductName":null,"ErrorMessage":null,"Status":0,"TrackingCode":null,"Invoiced":false,"OrderValue":0.0,"OrderCurrency":null,"TaxAmount":null,"ShippingAmount":null,"PlatformShippingAmount":null,"DiscountAmount":null,"SubTotal":null,"GrandTotal":null,"TotalPaid":null,"Manifested":false,"AddressChecked":false,"AddressValidated":false,"AddressCourierValidated":false,"ReturnJob":false,"DangerousGoods":false,"DangerousGoodsTypes":[],"Items":[],"TotalItemPrice":0.0,"Boxes":[],"AddressDetails":{"Building":null,"Company":null,"Street":"77 Santa Barbara Rd","City":"Pleasant Hill","Suburb":null,"Region":null,"State":"CA","PostCode":"94523","Country":"United States","CountryId":null,"Instructions":null,"TaxList":[]},"SenderDetails":null,"BillingAddress":null,"LastUpdatedatSource":"0001-01-01T00:00:00","IntegrationId":0,"ShippingMethod":"PARCEL POST + SIGNATURE","ShippingDescription":null,"PaymentMethod":null,"PaymentDescription":null,"StoreId":null,"StoreName":null,"DTP":null,"SignatureRequired":false,"ATL":false,"PackagingType":null,"ProductCode":null,"Contents":null,"Customs":{"Incoterm":0,"ExportReason":0,"documents":null,"InvoiceRemarks":null,"InvoiceText":null,"DutyAccountNumber":null},"Tags":[],"Version":null,"DutiesAmount":0.0,"IncludesFreight":false,"IncludesCustomsClearance":false,"Note":null,"DespatchPackageId":null}'}], 'declared_value': 0.0, 'archived': False, 'manifest_number': 0, 'writeback_status': '', 'address_validation': 'Valid', 'create_return': False, 'dtp': False, 'export_type': '', 'add_insurance': False, 'insurance_value': 0.0, 'plt': False, 'type': 'Outgoing', 'platform': 'API', 'status': 'Unshipped', 'manifested': False, 'has_commercial_invoice': False, 'is_fully_packed': False}, {'order_id': 541694218, 'order_date': '2025-04-01T10:19:57.2784764', 'order_number': '29', 'reference': 'Online Order', 'carrier': -1, 'carrier_name': '', 'carrier_service_code': '', 'shipping_method': 'PARCEL POST + SIGNATURE', 'signature_required': False, 'dangerous_goods': False, 'currency': 'USD', 'sender_details': {'name': 'Amit', 'email': 'amitchauhanwebkul@gmail.com', 'phone': '+919027504683', 'building': 'g-707', 'company': 'webkul', 'street': 'City Apartment Road', 'suburb': 'Shahpur Bamheta', 'city': 'Ghaziabad', 'state': 'UP', 'post_code': '201002', 'country': 'INDIA', 'tax_numbers': []}, 'destination': {'name': 'Deco Addict', 'email': 'deco_addict@yourcompany.example.com', 'phone': '(603)-996-3829', 'building': '', 'street': '77 Santa Barbara Rd', 'city': 'Pleasant Hill', 'state': 'CA', 'post_code': '94523', 'country': 'United States', 'delivery_instructions': '', 'tax_numbers': []}, 'packages': [{'package_id': 682298290, 'name': 'Package', 'weight': 2.0, 'height': 0.01, 'width': 0.05, 'length': 0.1, 'packaging_type': '', 'carrier_service_code': '', 'carrier_service_name': '', 'tracking_url': '', 'shipment_type': 'Outgoing'}], 'customs': {}, 'metadatas': [{'metafield_key': 'ADDRESSVALIDATED', 'value': 'True', 'required': False}, {'metafield_key': 'SOURCE', 'value': 'API', 'required': False}], 'events': [{'time': '2025-04-01T10:19:58.8566014', 'category': 'JSON', 'method': 'Imported from API', 'description': '{"Id":0,"AccountId":0,"Selected":false,"SequenceNumber":0,"SourceKey":null,"SequenceLong":0,"SequenceGuid":"00000000-0000-0000-0000-000000000000","SequenceStr":"29","OrginalSeqNumber":0,"AccountingAppId":0,"Date":"2025-04-01T10:19:57.2784764Z","ShipmentDate":"0001-01-01T00:00:00","To":"Deco Addict","CompanyName":null,"OurRef":"29","TheirRef":"Online Order","InvoiceId":null,"ConsigneeCode":null,"Email":"deco_addict@yourcompany.example.com","Telephone":"(603)-996-3829","AddressString":null,"ItemsString":null,"TrackingNumber":null,"CarrierCode":0,"CarrierName":null,"ProductName":null,"ErrorMessage":null,"Status":0,"TrackingCode":null,"Invoiced":false,"OrderValue":0.0,"OrderCurrency":null,"TaxAmount":null,"ShippingAmount":null,"PlatformShippingAmount":null,"DiscountAmount":null,"SubTotal":null,"GrandTotal":null,"TotalPaid":null,"Manifested":false,"AddressChecked":false,"AddressValidated":false,"AddressCourierValidated":false,"ReturnJob":false,"DangerousGoods":false,"DangerousGoodsTypes":[],"Items":[],"TotalItemPrice":0.0,"Boxes":[],"AddressDetails":{"Building":null,"Company":null,"Street":"77 Santa Barbara Rd","City":"Pleasant Hill","Suburb":null,"Region":null,"State":"CA","PostCode":"94523","Country":"United States","CountryId":null,"Instructions":null,"TaxList":[]},"SenderDetails":null,"BillingAddress":null,"LastUpdatedatSource":"0001-01-01T00:00:00","IntegrationId":0,"ShippingMethod":"PARCEL POST + SIGNATURE","ShippingDescription":null,"PaymentMethod":null,"PaymentDescription":null,"StoreId":null,"StoreName":null,"DTP":null,"SignatureRequired":false,"ATL":false,"PackagingType":null,"ProductCode":null,"Contents":null,"Customs":{"Incoterm":0,"ExportReason":0,"documents":null,"InvoiceRemarks":null,"InvoiceText":null,"DutyAccountNumber":null},"Tags":[],"Version":null,"DutiesAmount":0.0,"IncludesFreight":false,"IncludesCustomsClearance":false,"Note":null,"DespatchPackageId":null}'}], 'declared_value': 0.0, 'archived': False, 'manifest_number': 0, 'writeback_status': '', 'address_validation': 'Valid', 'create_return': False, 'dtp': False, 'export_type': '', 'add_insurance': False, 'insurance_value': 0.0, 'plt': False, 'type': 'Outgoing', 'platform': 'API', 'status': 'Unshipped', 'manifested': False, 'has_commercial_invoice': False, 'is_fully_packed': False}], 'success': True}
        if response['success'] == False:
            formatted_errors = "\n".join(
            [f"'message': '{error['message']}', 'details': '{error['details']}'" for error in response['errors']]
            )
            raise ValidationError(f"Success :-> False\n{formatted_errors}")
        else:
            for order in response.get('orders', []):
                track_link = sdk.request('GET',f'/api/track?order_number={order.get("order_number")}',{},header)
                # if track_link['results']['tracking_number']:
                #     track_number.append(track_link['results']['tracking_number'])
                pickings.message_post(body=f"Link :-> {track_link['results']['tracking_url']}")
                order_ids.append(order['order_id'])
            payload ={
                    "order_ids": order_ids
                    }
            pickings.write({'orders':order_ids})
            
            response = sdk.request('POST','/api/orders/shipments',payload,header)

            # response for test
            # response = {'labels': [{'label_type': 'BlankLabels', 'label_base64_string': 'JVBERi0xLjQKJeLjz9MKMiAwIG9iago8PC9UeXBlL0ZvbnQvU3VidHlwZS9UeXBlMS9CYXNlRm9udC9IZWx2ZXRpY2EtQm9sZC9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKMyAwIG9iago8PC9UeXBlL0ZvbnQvU3VidHlwZS9UeXBlMS9CYXNlRm9udC9IZWx2ZXRpY2EvRW5jb2RpbmcvV2luQW5zaUVuY29kaW5nPj4KZW5kb2JqCjQgMCBvYmoKPDwvVHlwZS9YT2JqZWN0L1N1YnR5cGUvSW1hZ2UvV2lkdGggNDA2L0hlaWdodCAxMzAvTGVuZ3RoIDc0L0NvbG9yU3BhY2UvRGV2aWNlR3JheS9CaXRzUGVyQ29tcG9uZW50IDgvRmlsdGVyL0ZsYXRlRGVjb2RlPj5zdHJlYW0KeJztwTEBAAAAwqD+qWcND6AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD+DJwIadgKZW5kc3RyZWFtCmVuZG9iago1IDAgb2JqCjw8L1R5cGUvWE9iamVjdC9TdWJ0eXBlL0ltYWdlL1dpZHRoIDQwNi9IZWlnaHQgMTMwL1NNYXNrIDQgMCBSL0xlbmd0aCA1NTk1L0NvbG9yU3BhY2VbL0NhbFJHQjw8L0dhbW1hWzIuMiAyLjIgMi4yXS9NYXRyaXhbMC40MTIzOSAwLjIxMjY0IDAuMDE5MzMgMC4zNTc1OCAwLjcxNTE3IDAuMTE5MTkgMC4xODA0NSAwLjA3MjE4IDAuOTUwNF0vV2hpdGVQb2ludFswLjk1MDQzIDEgMS4wOV0+Pl0vSW50ZW50L1BlcmNlcHR1YWwvQml0c1BlckNvbXBvbmVudCA4L0ZpbHRlci9GbGF0ZURlY29kZT4+c3RyZWFtCnic7ZDBEWU3DMPSf9ObAlaDALIOmXnfV4skyD9//hfvn+n9/SuF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6ztde3ZOF6R5uJHNNueIcGXgQAwOehnPd60T4yGAq19HYChJlqRQEnmP0us7XXt2ThekebiRzTbniHBl4EAMDnoZz3etE+MhgKtfR2AoSZakUBJ5j9LrO117dk4XpHm4kc0254hwZeBADA56Gc93rRPjIYCrX0dgKEmWpFASeY/S6zu/93u/93u/95/sXm3ArRQplbmRzdHJlYW0KZW5kb2JqCjYgMCBvYmoKPDwvTGVuZ3RoIDM5Mi9GaWx0ZXIvRmxhdGVEZWNvZGU+PnN0cmVhbQp4nH2SX1OCUBDF3/kU+2gP4t3L/940rdFMK3B6vsZVLBHFa+W3b0VAIaZhmLmwv7PsOctO6wUaA+4aumlDENK5fXkYBNqLtstuDiOqPdCZBAiMLgR0gFuYwbHWuacXDIKF1vLlJpTp7U3wUUHNC8oL9FvOPw/rOmkUZOtupY7Q3YpUxXKj4DURYR3mJexHItoeUuiJOJJKwOy5zmLJcoaM8XqdlfXhpD/snsoUQtUyWobO3Lrlx9m+1gzNC1f6xZ+naW84HuSdd4AeyyTcIgHqjkHu3dMQ7zF0VvESoZ9ANfUKRu3PLWhf7fJUH9rSTYuS8q4W4GTzTFPaFEwO8ZwWRkMyhm3zr23D8XSbvmk519vGsyWYLgAboiL/NCfaXHcvGiPTjJJoA368UlEltFxheqWCFwpOf59M0qUEX6VSqiadYee6ln8MN/LYxHCjYCb+Gy2csSYKWUF1D3uVivVKNGCeU1ANRdf8p+i4Vw7tzGADZV/n4GXUWIovCUJBmCRpnvkvlBLUSQplbmRzdHJlYW0KZW5kb2JqCjEgMCBvYmoKPDwvVHlwZS9QYWdlL01lZGlhQm94WzAgMCA0MjUuMiAyODMuNDZdL1Jlc291cmNlczw8L0ZvbnQ8PC9GMSAyIDAgUi9GMiAzIDAgUj4+L1hPYmplY3Q8PC9pbWcwIDQgMCBSL2ltZzEgNSAwIFI+Pj4+L1JvdGF0ZSA5MC9Db250ZW50cyA2IDAgUi9QYXJlbnQgNyAwIFI+PgplbmRvYmoKOSAwIG9iago8PC9UeXBlL1hPYmplY3QvU3VidHlwZS9JbWFnZS9XaWR0aCA0MDYvSGVpZ2h0IDEzMC9TTWFzayA0IDAgUi9MZW5ndGggNTA3Ny9Db2xvclNwYWNlWy9DYWxSR0I8PC9HYW1tYVsyLjIgMi4yIDIuMl0vTWF0cml4WzAuNDEyMzkgMC4yMTI2NCAwLjAxOTMzIDAuMzU3NTggMC43MTUxNyAwLjExOTE5IDAuMTgwNDUgMC4wNzIxOCAwLjk1MDRdL1doaXRlUG9pbnRbMC45NTA0MyAxIDEuMDldPj5dL0ludGVudC9QZXJjZXB0dWFsL0JpdHNQZXJDb21wb25lbnQgOC9GaWx0ZXIvRmxhdGVEZWNvZGU+PnN0cmVhbQp4nO2QWY5YIRADc/9LTw6QxlMFForE4xcv5f75+S/en+n9+wuNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+57Vn75mNSh80kNm2tDhHhnwQAhMyCef2ropRMVybs7JXolQRHHg+53vf+973vvfr+wvS7amqCmVuZHN0cmVhbQplbmRvYmoKMTAgMCBvYmoKPDwvTGVuZ3RoIDQwNy9GaWx0ZXIvRmxhdGVEZWNvZGU+PnN0cmVhbQp4nH2Sy1LCQBBF9/mKXuIicXomT3e8tFAENbFcD2YgKCESB5W/twkkkJiyUqma0Oc2fW/PxuhFBgPuC8t2IYrpbJ4+hpHxaGyKl8Mt1W7oTAIERg8CesAdLODUuLymHxhEc6MTqnWs8quL6K2G2ieUl+i3mr1vV01SlGSnv9Q76H7IXKdqreEpk3ET5hUcJjL52ObQk2mitITnhyaLFcsZMsabdVbVR5PBqLsvUwh1y+gIi/lNy3fPn41maJ+4yi/+3E97o/GwyYqSrQiz3w2HZm98dxxiAxiwQsEd6o2WJygofz/vawqXy3SBMMigvqAaRt0PLWi1ZnVq+nMs26FQg7NdecXo05yWCpNtOqPdkh/G0MS/CQkvsFz6T8c7vxh4cA/TObRo9lHRnOhyyz9pRKG5zZI1hOlSJ7XMjgo7qBS8VHC6qCrLFwpCnSul23TCPeo64S5eq10bw0XJTMIXuhuMtVHISqq7/dS5XC1lCxZ4JdVS9O1/ip5/5tAtDLZQ7nkOQUGNlfxSIDXEWZYfM/8Fo9fd8QplbmRzdHJlYW0KZW5kb2JqCjggMCBvYmoKPDwvVHlwZS9QYWdlL01lZGlhQm94WzAgMCA0MjUuMiAyODMuNDZdL1Jlc291cmNlczw8L0ZvbnQ8PC9GMSAyIDAgUi9GMiAzIDAgUj4+L1hPYmplY3Q8PC9pbWcwIDQgMCBSL2ltZzEgOSAwIFI+Pj4+L1JvdGF0ZSA5MC9Db250ZW50cyAxMCAwIFIvUGFyZW50IDcgMCBSPj4KZW5kb2JqCjExIDAgb2JqCjw8L1R5cGUvUGFnZS9NZWRpYUJveFswIDAgNDI1LjIgMjgzLjQ2XS9SZXNvdXJjZXM8PC9Gb250PDwvRjEgMiAwIFIvRjIgMyAwIFI+Pi9YT2JqZWN0PDwvaW1nMCA0IDAgUi9pbWcxIDkgMCBSPj4+Pi9Sb3RhdGUgOTAvQ29udGVudHMgMTAgMCBSL1BhcmVudCA3IDAgUj4+CmVuZG9iago3IDAgb2JqCjw8L1R5cGUvUGFnZXMvQ291bnQgMy9LaWRzWzEgMCBSIDggMCBSIDExIDAgUl0+PgplbmRvYmoKMTIgMCBvYmoKPDwvVHlwZS9DYXRhbG9nL1BhZ2VzIDcgMCBSPj4KZW5kb2JqCjEzIDAgb2JqCjw8L1Byb2R1Y2VyKGlUZXh0U2hhcnCSIDUuNS4xIKkyMDAwLTIwMTQgaVRleHQgR3JvdXAgTlYgXChBR1BMLXZlcnNpb25cKSkvQ3JlYXRpb25EYXRlKEQ6MjAyNTA0MDExMzI0NDcrMDAnMDAnKS9Nb2REYXRlKEQ6MjAyNTA0MDExMzI0NDcrMDAnMDAnKT4+CmVuZG9iagp4cmVmCjAgMTQKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDA2NzkzIDAwMDAwIG4gCjAwMDAwMDAwMTUgMDAwMDAgbiAKMDAwMDAwMDEwOCAwMDAwMCBuIAowMDAwMDAwMTk2IDAwMDAwIG4gCjAwMDAwMDA0MjUgMDAwMDAgbiAKMDAwMDAwNjMzNCAwMDAwMCBuIAowMDAwMDEzMTcyIDAwMDAwIG4gCjAwMDAwMTI4MjkgMDAwMDAgbiAKMDAwMDAwNjk2MyAwMDAwMCBuIAowMDAwMDEyMzU0IDAwMDAwIG4gCjAwMDAwMTMwMDAgMDAwMDAgbiAKMDAwMDAxMzIzNiAwMDAwMCBuIAowMDAwMDEzMjgyIDAwMDAwIG4gCnRyYWlsZXIKPDwvU2l6ZSAxNC9Sb290IDEyIDAgUi9JbmZvIDEzIDAgUi9JRCBbPDljZDg5ODM0ZjI0ZDIyYTMwNDQzOGRjMzlmNmNkYjVmPjw0ZTRmMDE3OGY3NjlkODQwMGE3ZjhiOWE5ZWYzZDZhZD5dPj4KJWlUZXh0LTUuNS4xCnN0YXJ0eHJlZgoxMzQ0NQolJUVPRgo='}], 'success': True, 'messages': []}
            if response['success'] == False:
                formatted_errors = "\n".join(
                [f"'message': '{error['message']}', 'details': '{error['details']}'" for error in response['errors']]
                )
                raise ValidationError(f"Success :-> False\n{formatted_errors}")
            else:
                label = response["labels"][0]["label_base64_string"]
                return [label,pickings.orders]
    
    
    def starshipit_send_shipping(self, pickings):
        result = {
            'exact_price': 0,
            'weight': 0, 
            'date_delivery': None,
            'tracking_number': '',
            'attachments': []
        }
        response = self.starshipit_create_shipments(pickings)
        result['tracking_number'] = ",".join(map(str, eval(response[1]))) 
        result['attachments'] = [(f'Label {pickings.sale_id.name}.pdf', base64.b64decode(response[0]))]
        return result
    
    @api.model
    def starshipit_get_return_label(self, pickings, tracking_number, origin_date):
        result = {'exact_price': 0, 'weight': 0, "date_delivery": None,
                    'tracking_number': '', 'attachments': []}
        response = self.starshipit_create_shipments(pickings,return_order=True)
        attachment = {
                'name': f'Return Label {self.name}.pdf',
                'datas': response[0],
                'res_model': 'stock.picking',
                'res_id': pickings.id,
            }
        pickings.carrier_tracking_ref = ",".join(map(str, eval(response[1])))
        attachment_id = self.env['ir.attachment'].create(attachment)
        pickings.message_post(
            body="Please find the attached PDF document.",
            attachment_ids=[attachment_id.id]
        )
        
        
    def _compute_can_generate_return(self):
        for carrier in self:
            carrier.can_generate_return = True
    
    
    def starshipit_cancel_shipment(self, pickings):
        config = self.wk_get_carrier_settings(['starshipit_api_key', 'starshipit_subscription_key'])
        sdk = StarShipItAPI(
            starshipit_api_key = config['starshipit_api_key'],
            starshipit_subscription_key = config['starshipit_subscription_key']
        )
        if not self.void_shipment:
            raise UserError('Shipment Cancelation not enabled')
        orders = ast.literal_eval(pickings.orders)
        for order in orders:
            header = sdk.get_starshipit_header()
            response = sdk.request('DELETE',f'/api/orders/delete?order_id={order}',{},header)
    
    
