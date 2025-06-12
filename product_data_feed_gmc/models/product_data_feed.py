from datetime import datetime
from lxml import etree as ET

from odoo import _, fields, models
from odoo.exceptions import UserError


class ProductDataFeed(models.Model):
    _inherit = "product.data.feed"

    recipient_is_gmc = fields.Boolean(compute='_compute_recipient_is_gmc')

    def _compute_recipient_is_gmc(self):
        for feed in self:
            feed.recipient_is_gmc = \
                feed.recipient_id == self.env.ref('product_data_feed_gmc.recipient_google_merchant_center')

    def _compute_cache_partial_is_enabled(self):
        res = super(ProductDataFeed, self)._compute_cache_partial_is_enabled()
        self.filtered('recipient_is_gmc').cache_partial_is_enabled = True
        return res

    def _xml_get_item_list_tag_name(self) -> str:
        """ Return an XML tag name for the item list element. """
        self.ensure_one()
        if not self.recipient_is_gmc:
            return super(ProductDataFeed, self)._xml_get_item_list_tag_name()
        return 'channel' if self.xml_specification == 'rss_2_0' \
            else '' if self.xml_specification == 'atom_1_0' \
            else ''

    def _xml_get_item_tag_name(self) -> str:
        """ Return an XML tag name for the item element. """
        self.ensure_one()
        if not self.recipient_is_gmc:
            return super(ProductDataFeed, self)._xml_get_item_tag_name()
        return 'item' if self.xml_specification == 'rss_2_0' \
            else 'entry' if self.xml_specification == 'atom_1_0' \
            else ''

    # pylint: disable-msg=too-many-locals,too-many-branches,too-many-nested-blocks
    def generate_data_file_xml(self):
        """ Generate data feed XML file """
        self.ensure_one()
        if not self.recipient_is_gmc:
            return super(ProductDataFeed, self).generate_data_file_xml()

        feed = self
        namespace = 'http://base.google.com/ns/1.0'

        def get_ns(name):
            return '{%s}%s' % (namespace, name)

        if feed.xml_specification == 'rss_2_0':

            xml_feed = ET.Element('rss', nsmap={'g': namespace}, version='2.0')
            channel = ET.SubElement(xml_feed, 'channel')
            ET.SubElement(channel, 'title').text = feed.name
            ET.SubElement(channel, 'description').text = feed.name
            ET.SubElement(channel, 'link').text = feed._get_base_url()
            items_element = channel
            item_tag = 'item'

        elif feed.xml_specification == 'atom_1_0':
            namespace_atom = 'http://www.w3.org/2005/Atom'
            xml_feed = ET.Element('feed', nsmap={None: namespace_atom, 'g': namespace})
            ET.SubElement(xml_feed, 'title').text = self.name
            ET.SubElement(xml_feed, 'link', rel='self', href=self._get_base_url())
            ET.SubElement(xml_feed, 'updated').text = datetime.strftime(fields.Datetime.now(), "%Y-%m-%dT%H:%M:%S%Z")
            items_element = xml_feed
            item_tag = 'entry'

        else:
            raise UserError(_("Specify the XML specification."))

        # Add or skip XML root for partial caching
        if self._context.get('without_headers', False):
            xml_feed = ET.Element('data_feed_items')
            items_element = xml_feed

        for product in self.get_items_with_context():
            item = ET.SubElement(items_element, item_tag)

            for column in self.column_ids:
                value = column._get_value(product)

                # Multi values
                if column.multi_value_type:
                    value_list = value

                    if column.multi_value_type == 'list_of_dict':
                        for val in value_list:
                            dict_item = ET.SubElement(item, get_ns(column.name))

                            if column.multi_dict_keys:
                                for key in column.multi_dict_keys.split(','):
                                    ET.SubElement(dict_item, get_ns(key)).text = val[key]

                            # Use "multi_dict_key" and "multi_dict_value"
                            else:
                                ET.SubElement(
                                    dict_item, get_ns(column.multi_dict_key),
                                ).text = val[column.multi_dict_key]
                                ET.SubElement(
                                    dict_item, get_ns(column.multi_dict_value),
                                ).text = val[column.multi_dict_value]

                    else:
                        if column.multi_value_type == 'string':
                            try:
                                value_list = value.split(column.multi_value_separator)
                            except ValueError:
                                value_list = value

                        column_number = 0
                        for val in value_list:
                            column_name = column.name
                            if column.multi_suffix == 'number':
                                column_name = "%s%d" % (column.name, column_number)
                            ET.SubElement(item, get_ns(column_name)).text = val
                            column_number += 1

                # Single value
                else:
                    ET.SubElement(item, get_ns(column.name)).text = value

        feed._post_warnings()

        return ET.tostring(xml_feed, xml_declaration=True, encoding='UTF-8')
