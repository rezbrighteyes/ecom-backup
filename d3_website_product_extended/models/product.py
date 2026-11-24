import re
from odoo import api, fields, models, _
from odoo.http import request
from odoo.fields import Domain
from itertools import product


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    D3_DISPLAYABLE_STUDIO_SPEC_TYPES = {
        'char', 'text', 'selection', 'boolean', 'integer', 'float', 'monetary',
        'date', 'datetime', 'many2one',
    }
    D3_FILTERABLE_STUDIO_SPEC_TYPES = {
        'char', 'selection', 'boolean', 'integer', 'float', 'monetary',
        'date', 'datetime', 'many2one',
    }
    D3_EXCLUDED_AUTO_STUDIO_SPEC_TERMS = {
        'neto reference',
    }
    D3_FILTERABLE_SPEC_FIELDS = [
        ('d3_specific_size', _('Size')),
        ('d3_specific_shape', _('Shape')),
        ('d3_lens_technology', _('Lens Technology')),
        ('d3_lens_material', _('Lens Material')),
        ('d3_lens_colour', _('Lens Colour')),
        ('d3_lens_category', _('Lens Category')),
        ('d3_frame_material', _('Frame Material')),
        ('d3_frame_colour', _('Frame Colour')),
        ('d3_base_curve', _('Base Curve')),
        ('d3_bridge_size', _('Bridge Size')),
        ('d3_lens_height', _('Lens Height')),
        ('d3_lens_width', _('Lens Width')),
        ('d3_temple_length', _('Temple Length')),
    ]

    d3_model_code = fields.Char(string='Model Code', index=True)
    d3_warranty = fields.Text(string='Warranty')
    d3_store_range = fields.Boolean(string='Store Range')
    d3_online_range = fields.Boolean(string='Online Range')
    d3_clearance = fields.Boolean(string='Clearance')
    d3_discontinued = fields.Boolean(string='Discontinued')
    d3_gender = fields.Char(string='Gender')
    d3_specific_size = fields.Char(string='Size')
    d3_specific_shape = fields.Char(string='Shape')
    d3_lens_technology = fields.Char(string='Lens Technology')
    d3_lens_material = fields.Char(string='Lens Material')
    d3_lens_colour = fields.Char(string='Lens Colour')
    d3_lens_category = fields.Char(string='Lens Category')
    d3_frame_material = fields.Char(string='Frame Material')
    d3_frame_colour = fields.Char(string='Frame Colour')
    d3_base_curve = fields.Char(string='Base Curve')
    d3_bridge_size = fields.Char(string='Bridge Size')
    d3_lens_height = fields.Char(string='Lens Height')
    d3_lens_width = fields.Char(string='Lens Width')
    d3_temple_length = fields.Char(string='Temple Length')
    d3_hidden_website_spec_field_ids = fields.Many2many(
        'ir.model.fields',
        'd3_product_template_hidden_website_spec_field_rel',
        'product_tmpl_id',
        'field_id',
        string='Excluded Website Specification Fields',
    )
    d3_hidden_website_spec_field_names = fields.Text(
        string='Excluded Website Specification Field Names',
        compute='_compute_d3_hidden_website_spec_field_names',
        store=True,
    )

    @api.depends('d3_hidden_website_spec_field_ids')
    def _compute_d3_hidden_website_spec_field_names(self):
        for product in self:
            product.d3_hidden_website_spec_field_names = ''.join(
                f'|{field.name}|'
                for field in product.d3_hidden_website_spec_field_ids
                if field.model == 'product.template' and field.name in product._fields
            )

    @api.model
    def _d3_get_filterable_spec_fields(self):
        fields_specs = list(self.D3_FILTERABLE_SPEC_FIELDS)
        existing_fields = {field_name for field_name, label in fields_specs}
        fields_specs.extend([
            (field_name, label)
            for field_name, label in self._d3_get_studio_spec_fields(filterable_only=True)
            if field_name not in existing_fields
        ])
        return self._d3_sort_spec_fields_by_backend_view(fields_specs)

    @api.model
    def _d3_get_studio_spec_fields(self, filterable_only=False):
        allowed_types = (
            self.D3_FILTERABLE_STUDIO_SPEC_TYPES
            if filterable_only else self.D3_DISPLAYABLE_STUDIO_SPEC_TYPES
        )
        specs_view_order = set(self._d3_get_specs_backend_view_field_order())
        studio_fields = self.env['ir.model.fields'].sudo().search([
            ('model', '=', 'product.template'),
            ('name', '=like', 'x_studio_%'),
            ('store', '=', True),
            ('ttype', 'in', list(allowed_types)),
        ], order='field_description, name')
        fields_specs = [
            (field.name, field.field_description or field.name)
            for field in studio_fields
            if field.name in self._fields
            and field.name in specs_view_order
            and not self._d3_is_excluded_auto_studio_spec_field(field)
        ]
        return self._d3_sort_spec_fields_by_backend_view(fields_specs)

    @api.model
    def _d3_is_excluded_auto_studio_spec_field(self, field):
        field_text = f'{field.name} {field.field_description or ""}'.lower().replace('_', ' ')
        return any(term in field_text for term in self.D3_EXCLUDED_AUTO_STUDIO_SPEC_TERMS)

    @api.model
    def _d3_get_specs_backend_view_field_order(self):
        field_names = []
        seen_fields = set()
        for view_xmlid in (
            'product.product_template_only_form_view',
            'product.product_template_form_view',
            'website_sale.product_template_form_view',
        ):
            product_form_view = self.env.ref(view_xmlid, raise_if_not_found=False)
            if not product_form_view:
                continue
            try:
                combined_arch = product_form_view.sudo()._get_combined_arch()
            except Exception:
                continue

            specs_pages = combined_arch.xpath("//page[@name='d3_specifications_filters']")
            if not specs_pages:
                continue

            for field_node in specs_pages[0].xpath(".//field[@name]"):
                field_name = field_node.get('name')
                if field_name and field_name not in seen_fields:
                    field_names.append(field_name)
                    seen_fields.add(field_name)
        return field_names

    @api.model
    def _d3_sort_spec_fields_by_backend_view(self, fields_specs):
        specs_view_order = self._d3_get_specs_backend_view_field_order()
        if not specs_view_order:
            return fields_specs
        order_by_field = {
            field_name: index
            for index, field_name in enumerate(specs_view_order)
        }
        fallback_index = len(order_by_field)
        return [
            fields_spec
            for original_index, fields_spec in sorted(
                enumerate(fields_specs),
                key=lambda item: (
                    order_by_field.get(item[1][0], fallback_index + item[0]),
                    item[0],
                ),
            )
        ]

    @api.model
    def _d3_get_selected_website_spec_filters(self):
        selected_filters = {}
        filterable_fields = {field for field, label in self._d3_get_filterable_spec_fields()}
        # Two shapes: a full page load repeats `d3_spec_filter=field:value`
        # in the query string; the Odoo 20 /shop/reload JSON call sends ONE
        # comma-joined value (see static/src/interactions/shop_page_spec_filters.js).
        try:
            raw_filters = list(request.httprequest.args.getlist('d3_spec_filter'))
            param = request.params.get('d3_spec_filter')
        except RuntimeError:
            raw_filters, param = [], None
        for item in (param if isinstance(param, list) else [param] if param else []):
            if item not in raw_filters:
                raw_filters.append(item)
        expanded = []
        for raw_filter in raw_filters:
            # Split "a:1,b:2" only before a "field:" prefix, so a comma inside
            # a value ("50,5") survives.
            expanded.extend(re.split(r',(?=[a-z_][a-z0-9_]*:)', raw_filter or ''))
        for raw_filter in expanded:
            if not raw_filter or ':' not in raw_filter:
                continue
            field_name, value = raw_filter.split(':', 1)
            value = value.strip()
            if field_name in filterable_fields and value:
                selected_filters.setdefault(field_name, set()).add(value)
        return selected_filters

    @api.model
    def _d3_get_spec_filter_keys(self, selected_filters):
        return {
            self._d3_get_spec_filter_key(field_name, value)
            for field_name, values in selected_filters.items()
            for value in values
        }

    @api.model
    def _d3_get_spec_filter_key(self, field_name, value):
        return f'{field_name}:{self._d3_stringify_spec_filter_value(field_name, value)}'

    @api.model
    def _d3_stringify_spec_filter_value(self, field_name, value):
        field = self._fields.get(field_name)
        if not field:
            return str(value)
        if field.type == 'many2one':
            if isinstance(value, (list, tuple)):
                return str(value[0])
            return str(value.id if hasattr(value, 'id') else value)
        if field.type == 'boolean':
            return '1' if value else '0'
        if field.type in ('date', 'datetime') and value:
            return fields.Datetime.to_string(value) if field.type == 'datetime' else fields.Date.to_string(value)
        return str(value)

    @api.model
    def _d3_parse_spec_filter_value(self, field_name, value):
        field = self._fields.get(field_name)
        if not field:
            return value
        if field.type in ('many2one', 'integer'):
            try:
                return int(value)
            except (TypeError, ValueError):
                return False
        if field.type in ('float', 'monetary'):
            try:
                return float(value)
            except (TypeError, ValueError):
                return False
        if field.type == 'boolean':
            return value in ('1', 'true', 'True')
        return value

    @api.model
    def _d3_get_spec_filter_domain(self, selected_filters):
        domains = []
        for field_name, values in selected_filters.items():
            field_domains = [
                Domain.AND([
                    [(field_name, '=', self._d3_parse_spec_filter_value(field_name, value))],
                    self._d3_get_website_visible_spec_domain(field_name),
                ])
                for value in values
            ]
            if field_domains:
                domains.append(Domain.OR(field_domains))
        return Domain.AND(domains) if domains else []

    @api.model
    def _d3_get_present_value_domain(self, field_name):
        field = self._fields.get(field_name)
        if field and field.type == 'boolean':
            return [(field_name, '=', True)]
        if field and field.type in ('char', 'text', 'selection'):
            return [(field_name, '!=', False), (field_name, '!=', '')]
        return [(field_name, '!=', False)]

    @api.model
    def _d3_get_website_visible_spec_domain(self, field_name):
        return Domain.OR([
            [('d3_hidden_website_spec_field_names', '=', False)],
            [('d3_hidden_website_spec_field_names', 'not ilike', f'|{field_name}|')],
        ])

    def _d3_is_spec_hidden_on_website(self, field_name):
        self.ensure_one()
        return f'|{field_name}|' in (self.d3_hidden_website_spec_field_names or '')

    @api.model
    def _d3_format_spec_value(self, field_name, value):
        field = self._fields.get(field_name)
        if not field or not value:
            return value
        if field.type == 'many2one':
            if isinstance(value, (list, tuple)):
                return value[1]
            return value.display_name
        if field.type == 'boolean':
            return _('Yes') if value else ''
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value)
        return value

    @api.model
    def _d3_get_website_spec_filter_values(self, products, selected_filter_keys=None):
        selected_filter_keys = selected_filter_keys or set()
        filters = []
        ProductTemplate = self.env['product.template'].sudo()
        product_ids = products.ids
        if not product_ids:
            return filters

        for field_name, label in self._d3_get_filterable_spec_fields():
            # Odoo 20: read_group returns (value, count) tuples; a many2one
            # value is a record, which the key/format helpers accept.
            groups = ProductTemplate.read_group(
                Domain('id', 'in', product_ids)
                & Domain(self._d3_get_present_value_domain(field_name))
                & self._d3_get_website_visible_spec_domain(field_name),
                [field_name],
                ['__count'],
            )
            values = []
            for value, count in groups:
                if not value:
                    continue
                key = self._d3_get_spec_filter_key(field_name, value)
                values.append({
                    'key': key,
                    'label': self._d3_format_spec_value(field_name, value),
                    'count': count,
                    'selected': key in selected_filter_keys,
                })
            values = sorted(values, key=lambda item: str(item['label']).lower())
            if values:
                filters.append({
                    'field': field_name,
                    'label': label,
                    'values': values,
                    'selected': any(value['selected'] for value in values),
                })
        return filters

    @api.model
    def _search_get_detail(self, website, order, options):
        result = super()._search_get_detail(website, order, options)
        selected_filters = self._d3_get_selected_website_spec_filters()
        spec_filter_domain = self._d3_get_spec_filter_domain(selected_filters)
        if spec_filter_domain:
            # `base_domain` is a LIST of domains that the search ANDs together.
            result['base_domain'] = list(result['base_domain']) + [spec_filter_domain]
        return result

    def _d3_get_visible_product_specs(self, group=False):
        self.ensure_one()
        spec_groups = {
            'general': [
                ('d3_specific_size', _('Size')),
                ('d3_specific_shape', _('Shape')),
                ('d3_lens_technology', _('Lens Technology')),
                ('d3_lens_colour', _('Lens Colour')),
                ('d3_lens_category', _('Lens Category')),
                ('d3_frame_colour', _('Frame Colour')),
            ],
            'size': [
                ('d3_base_curve', _('Base Curve')),
                ('d3_bridge_size', _('Bridge Size')),
                ('d3_lens_height', _('Lens Height')),
                ('d3_lens_width', _('Lens Width')),
                ('d3_temple_length', _('Temple Length')),
            ],
            'material': [
                ('d3_lens_material', _('Lens Material')),
                ('d3_frame_material', _('Frame Material')),
            ],
        }
        field_specs = spec_groups.get(group) or sum(spec_groups.values(), [])
        if group in (False, 'general'):
            existing_fields = {field_name for field_name, label in field_specs}
            field_specs += [
                (field_name, label)
                for field_name, label in self._d3_get_studio_spec_fields(filterable_only=False)
                if field_name not in existing_fields
            ]
            field_specs = self._d3_sort_spec_fields_by_backend_view(field_specs)
        visible_specs = []
        for field_name, label in field_specs:
            if self._d3_is_spec_hidden_on_website(field_name):
                continue
            value = self[field_name]
            if value:
                visible_specs.append((label, self._d3_format_spec_value(field_name, value)))
        return visible_specs

    def get_selected_variants(self):
        variants = self.env['product.product']
        product_variants = self.product_variant_ids
        attribute_line_ids = self.attribute_line_ids.filtered(lambda x: x.show_in_website)
        if attribute_line_ids:
            cmb_list = [line.mapped('value_ids.id') for line in attribute_line_ids]
            combinations = list(map(list, product(*cmb_list)))
            for c in combinations:
                variant = self.env['product.product']
                for pv in product_variants:
                    if all(cc in pv.product_template_variant_value_ids.mapped('product_attribute_value_id.id') for
                           cc in c):
                        variant |= pv
                if variant:
                    variants |= variant[0]
        elif self.env.website.shop_one_card_per_product:
            variants |= product_variants[:1]
        else:
            variants |= product_variants
        return variants


class Product(models.Model):
    _inherit = 'product.product'


    def _get_sales_prices(self, website):
        """Shop-card prices per VARIANT, keyed by variant id.

        Mirrors ``product.template._get_sales_prices`` (Odoo 20) for variants,
        so each variant card shows its own price, including price extras.
        Kept on ``website`` only, because the Rockos homepage calls it that way.
        """
        if not self:
            return {}

        pricelist_sudo = website.sudo()._get_and_cache_current_pricelist()
        fiscal_position_sudo = website.sudo()._get_and_cache_current_fiscal_position()
        currency = website.currency_id
        ProductTemplate = self.env['product.template']

        pricelist_prices = pricelist_sudo._compute_price_rule(self, 1.0)
        comparison_prices_enabled = self.env['res.groups']._is_feature_enabled(
            'website_sale.group_product_price_comparison'
        )

        res = {}
        for variant in self:
            pricelist_price, pricelist_rule_id = pricelist_prices[variant.id]
            product_taxes = variant.sudo().taxes_id._filter_taxes_by_company()
            taxes = fiscal_position_sudo.map_tax(product_taxes)

            base_price = None
            price_vals = {
                'price_reduce': ProductTemplate._apply_taxes_to_price(
                    pricelist_price, currency, product=variant,
                    product_taxes=product_taxes, taxes=taxes, website=website,
                ),
            }
            pricelist_item_sudo = self.env['product.pricelist.item'].sudo().browse(pricelist_rule_id)
            if pricelist_item_sudo._show_discount_on_shop():
                pricelist_base_price = pricelist_item_sudo._compute_price_before_discount(
                    product=variant, quantity=1.0, uom=variant._get_main_uom(), currency=currency,
                )
                if currency.compare_amounts(pricelist_base_price, pricelist_price) == 1:
                    base_price = pricelist_base_price
                    price_vals['base_price'] = ProductTemplate._apply_taxes_to_price(
                        base_price, currency, product=variant,
                        product_taxes=product_taxes, taxes=taxes, website=website,
                    )

            if not base_price and comparison_prices_enabled and variant.compare_list_price:
                price_vals['base_price'] = variant.currency_id._convert(
                    variant.compare_list_price, currency, self.env.company, round=False,
                )

            res[variant.id] = price_vals
        return res

    def _get_combination_info_variant(self, **kwargs):
        res = super()._get_combination_info_variant(**kwargs)
        combination = self.product_template_variant_value_ids
        variant_attributes = []
        for cmb in combination:
            variant_attributes.append([cmb.attribute_id.name, cmb.name])
        res['variant_attributes'] = variant_attributes
        return res

    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get('website_id'):
            for product in self:
                variant_display_name = product.display_name
                variant_names = []
                selected_attributes = product.product_tmpl_id.attribute_line_ids.filtered(lambda x: x.show_in_website)
                for vv in product.product_template_variant_value_ids:
                    if vv.attribute_id.id in selected_attributes.mapped('attribute_id.id'):
                        variant_names.append(vv.name)
                if variant_names:
                    variant_display_name = f"{product.name} ({', '.join(variant_names)})"
                product.display_name = variant_display_name



class ProductTemplateAttributeLine(models.Model):
    _inherit = 'product.template.attribute.line'

    show_in_website = fields.Boolean()
