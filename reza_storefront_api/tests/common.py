# -*- coding: utf-8 -*-
"""Fixture shared by the catalogue tests.

Two websites (W, the one under test, and OTHER) in one company, plus a second
company, and one product per scope rule. The database may already hold real
products (the Odoo 18 copy is a production restore), so tests assert presence,
absence and uniqueness, never an exact set. Barcodes are generated so they
cannot collide with real ones.
"""

import io
import uuid

from PIL import Image

from odoo import Command, release
from odoo.tools.binary import BinaryBytes  # 18/20: base64 on 18

# 32+ characters (shorter tokens close the endpoint) and non-ASCII on purpose.
TOKEN = "sf-test-token-é-7c1d-0123456789abcdef-xyz"
ODOO_MAJOR = release.version_info[0]


def png(colour=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), colour).save(buf, format="PNG")
    return BinaryBytes(buf.getvalue())  # 18/20: base64.b64encode(...) on 18


def blob(raw):
    """Raw bytes as a Binary field value."""
    return BinaryBytes(raw)  # 18/20: base64.b64encode(raw) on 18


def fake_barcode():
    return "SFT" + uuid.uuid4().hex[:12]


class CatalogueFixture:

    @classmethod
    def _set_token(cls, value):
        cls.params.set_str("reza_storefront_api.token", value)  # 18/20: set_param on 18

    @classmethod
    def _set_access(cls, team, aud):
        """Cloudflare Access settings; None deletes the parameter."""
        for key, value in (("reza_storefront_api.access_team_domain", team),
                           ("reza_storefront_api.access_aud", aud)):
            if value is None:
                cls.params.search([("key", "=", key)]).unlink()
            else:
                cls.params.set_str(key, value)  # 18/20: set_param on 18

    @classmethod
    def _setup_catalogue(cls):
        env = cls.env
        cls.params = env["ir.config_parameter"].sudo()
        cls._set_token(TOKEN)
        # The database may carry Access settings: start from token-only.
        cls._set_access(None, None)
        company = env.company
        cls.website = env["website"].create({
            "name": "SF Test Site",
            "company_id": company.id,
            "domain": "https://sf-test.example",
        })
        cls.other_website = env["website"].create({
            "name": "SF Other Site",
            "company_id": company.id,
        })
        cls.other_company = env["res.company"].create({"name": "SF Other Company"})
        cls.brand = env["product.data.feed.brand"].create({"name": "Sf Test Brand"})
        cls.colour = env["product.attribute"].create({
            "name": "SF Colour",
            "display_type": "color",
            "create_variant": "always",
            "value_ids": [
                Command.create({"name": "SF Black", "html_color": "#000000"}),
                Command.create({"name": "SF Red", "html_color": "#ff0000"}),
            ],
        })
        cls.hidden_attr = env["product.attribute"].create({
            "name": "SF Internal Batch",
            "create_variant": "always",
            "visibility": "hidden",
            "value_ids": [Command.create({"name": "SF Batch 7"})],
        })
        cls.size = env["product.attribute"].create({
            "name": "SF Size",
            "create_variant": "always",
            "value_ids": [
                Command.create({"name": "SF Small"}),
                Command.create({"name": "SF Large"}),
            ],
        })
        cls.lens = env["product.attribute"].create({
            "name": "SF Lens",
            "create_variant": "no_variant",
            "display_type": "radio",
            "value_ids": [
                Command.create({"name": "SF Standard", "sequence": 1}),
                Command.create({"name": "SF Premium", "sequence": 2}),
            ],
        })
        cls.category = env["product.public.category"].create({
            "name": "SF Sunglasses",
            "website_meta_title": "SF Sunglasses title",
        })
        cls.foreign_category = env["product.public.category"].create({
            "name": "SF Other-site Category",
            "website_id": cls.other_website.id,
        })
        cls.empty_category = env["product.public.category"].create({
            "name": "SF Empty Prelaunch Category",
        })
        # A shared child under a parent that belongs to another website.
        cls.foreign_parent = env["product.public.category"].create({
            "name": "SF Private Parent",
            "website_id": cls.other_website.id,
        })
        cls.shared_child = env["product.public.category"].create({
            "name": "SF Shared Child",
            "parent_id": cls.foreign_parent.id,
        })
        cls.ribbon = env["product.ribbon"].create({
            "name": "SF Sale", "bg_color": "#ff0000", "text_color": "#ffffff",
        })

        def tmpl(name, **vals):
            base = {
                "name": name,
                "type": "consu",
                "is_storable": True,
                "list_price": 100.0,
                "sale_ok": True,
                "is_published": True,
                "website_ids": [Command.set(cls.website.ids)],
                "allow_out_of_stock_order": True,
                "taxes_id": [Command.clear()],
            }
            base.update(vals)
            return env["product.template"].create(base)

        cls.make_template = staticmethod(tmpl)
        cls.pub = tmpl(
            "SF Published Glasses",
            feed_brand_id=cls.brand.id,
            public_categ_ids=[Command.set(
                (cls.category | cls.foreign_category | cls.shared_child).ids)],
            description_sale="SF sale text",
            website_meta_title="SF shared title",
            website_meta_keywords="sf, glasses",
            compare_list_price=150.0,
            website_ribbon_id=cls.ribbon.id,
            image_1920=png(),
            attribute_line_ids=[
                Command.create({
                    "attribute_id": cls.colour.id,
                    "value_ids": [Command.set(cls.colour.value_ids.ids)],
                }),
                Command.create({
                    "attribute_id": cls.hidden_attr.id,
                    "value_ids": [Command.set(cls.hidden_attr.value_ids.ids)],
                }),
            ],
        )
        for variant in cls.pub.product_variant_ids:
            variant.barcode = fake_barcode()
        cls.shared = tmpl("SF Shared Glasses", website_ids=[Command.clear()])
        cls.sized = tmpl("SF Sized Glasses", attribute_line_ids=[Command.create({
            "attribute_id": cls.size.id,
            "value_ids": [Command.set(cls.size.value_ids.ids)],
        })])
        cls.large_value = cls.size.value_ids.filtered(lambda v: v.name == "SF Large")
        cls.sized.product_variant_ids.filtered(
            lambda v: cls.large_value
            in v.product_template_attribute_value_ids.product_attribute_value_id
        ).active = False
        cls.with_lens = tmpl("SF Lens Glasses", attribute_line_ids=[Command.create({
            "attribute_id": cls.lens.id,
            "value_ids": [Command.set(cls.lens.value_ids.ids)],
        })])
        ptavs = cls.with_lens.attribute_line_ids.product_template_value_ids
        ptavs.filtered(lambda p: p.name == "SF Standard").price_extra = 20.0
        ptavs.filtered(lambda p: p.name == "SF Premium").price_extra = 35.0

        cls.unpublished = tmpl("SF Unpublished Glasses", is_published=False)
        cls.foreign = tmpl("SF Other Site Glasses",
                           website_ids=[Command.set(cls.other_website.ids)])
        cls.not_for_sale = tmpl("SF Not For Sale Glasses", sale_ok=False)
        cls.archived = tmpl("SF Archived Glasses")
        cls.archived.active = False
        cls.other_company_product = tmpl(
            "SF Other Company Glasses", website_ids=[Command.clear()],
            company_id=cls.other_company.id)
        cls.single_site_other = tmpl(
            "SF Core Website-Id Other Glasses", website_ids=[Command.clear()],
            website_id=cls.other_website.id)
        cls.excluded = (cls.unpublished | cls.foreign | cls.not_for_sale | cls.archived
                        | cls.other_company_product | cls.single_site_other)


# Exact key sets of contract v1. Literals on purpose: the allowlist test must
# not derive the expected keys from the code it is checking.
META_KEYS = {"contract", "generated_at", "website", "categories", "brands", "product_count",
             "default_sort", "content_version", "refresh_requested_at", "next_content_change_at"}
WEBSITE_KEYS = {"id", "name", "domain", "currency", "lang", "prices_include_tax",
                "products_per_page", "logo_url"}
CATEGORY_KEYS = {"id", "name", "parent_id", "sequence", "url", "meta_title",
                 "meta_description", "image_url"}
BRAND_KEYS = {"id", "name", "slug"}
PAGE_KEYS = {"contract", "page", "limit", "product_count", "next_page", "products"}
PRODUCT_KEYS = {"id", "name", "url", "write_date", "description_html", "description_sale",
                "meta_title", "meta_description", "meta_keywords", "category_ids",
                "brand_id", "ribbon", "images", "attributes", "variants", "price_min",
                "price_max", "rating", "sort"}
SORT_KEYS = {"website_sequence", "create_date", "publish_date", "list_price", "name_rank"}
RIBBON_KEYS = {"name", "bg", "text"}
IMAGE_KEYS = {"url", "alt"}
ATTRIBUTE_KEYS = {"id", "name", "display_type", "show_in_website", "values"}
VALUE_KEYS = {"id", "name", "html_color"}
VARIANT_KEYS = {"id", "default_code", "barcode", "value_ids", "image_url", "price",
                "compare_price", "currency", "available_qty_band", "available_qty",
                "allow_out_of_stock_order", "url"}
RATING_KEYS = {"avg", "count"}
BANDS = {"in_stock", "low", "out"}
