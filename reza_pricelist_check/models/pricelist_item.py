# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .pricelist import REPORT_RULES_KEY


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    # Stored so the Price Rules screen can group and search on it. A category
    # rule carries its own category; a product or variant rule takes the
    # product's.
    reza_category_id = fields.Many2one(
        "product.category", string="Category Group", compute="_compute_reza_grouping",
        store=True, index=True)
    reza_kind = fields.Selection(
        [("pct", "% Off"), ("fixed", "Fixed Price"), ("formula", "Formula"),
         ("full", "Full Price")],
        string="Type", compute="_compute_reza_rule_text",
        help="Full Price is a 0% rule: it keeps the normal price, usually to "
             "exclude a product or category from a wider discount.")
    reza_rule_text = fields.Char(
        string="Rule", compute="_compute_reza_rule_text",
        help="What the rule does, in words: a fixed price, a % off the normal "
             "price, or a % off another list's price.")
    reza_sale_price = fields.Float(
        string="Normal Price", compute="_compute_reza_works_out", digits="Product Price",
        help="The Sale Price on the product, before any list.")
    reza_rule_price = fields.Float(
        string="This List Charges", compute="_compute_reza_works_out", digits="Product Price",
        help="What a customer on this list pays for one unit today. Blank for "
             "category and all-product rules, which cover many products: use "
             "Check Prices on the list to see each one.")
    reza_off_pct = fields.Float(
        string="% Off", compute="_compute_reza_works_out",
        help="How far This List Charges sits below the Normal Price.")
    reza_dates_text = fields.Char(string="Dates", compute="_compute_reza_dates")
    reza_date_state = fields.Selection(
        [("always", "Always"), ("running", "Running"), ("expired", "Expired"),
         ("future", "Not started")],
        string="Date Status", compute="_compute_reza_dates",
        help="Expired and not-started rules are ignored when an order is priced.")
    reza_in_use = fields.Boolean(
        string="In Use", compute="_compute_reza_works_out", search="_search_reza_in_use",
        help="Ticked when this is the rule the list actually picks for the "
             "product today. Unticked means another rule on the same list "
             "wins, or the rule's dates are not running, so it changes nothing.")

    @api.depends("applied_on", "categ_id", "product_tmpl_id.categ_id", "product_id.categ_id")
    def _compute_reza_grouping(self):
        for item in self:
            tmpl = item.product_id.product_tmpl_id or item.product_tmpl_id
            item.reza_category_id = item.categ_id if item.applied_on == "2_product_category" else tmpl.categ_id

    def _reza_in_use_ids(self):
        """Ids of the product and variant rules in self that their list picks.

        One rule search per list, not one per rule.
        """
        now = fields.Datetime.now()
        in_use = set()
        for pricelist in self.mapped("pricelist_id"):
            items = self.filtered(lambda i: i.pricelist_id == pricelist)
            samples = {item: item._reza_sample_product() for item in items}
            samples = {item: p for item, p in samples.items() if p}
            if not samples:
                continue
            company = pricelist.company_id or self.env.company
            products = self.env["product.product"].union(*samples.values())
            state = {"date": now, "ids": {"product.product": frozenset(products.ids)}, "rules": {}}
            engine = pricelist.with_company(company).with_context(**{REPORT_RULES_KEY: state})
            winner = {}
            for product in products.with_company(company):
                winner[product.id] = engine._get_product_rule(product, 1.0, date=now)
            in_use.update(item.id for item, p in samples.items() if winner.get(p.id) == item.id)
        return in_use

    def _search_reza_in_use(self, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            return NotImplemented
        values = {bool(v) for v in value} if isinstance(value, (list, tuple, set)) else {bool(value)}
        positive = (True in values) if operator in ("=", "in") else (True not in values)
        rules = self.search([("applied_on", "in", ("0_product_variant", "1_product"))])
        ids = list(rules._reza_in_use_ids())
        return [("id", "in" if positive else "not in", ids)]

    def _compute_reza_works_out(self):
        now = fields.Datetime.now()
        in_use = self._reza_in_use_ids()
        for item in self:
            item.reza_sale_price = item.reza_rule_price = item.reza_off_pct = 0.0
            item.reza_in_use = False
            product = item._reza_sample_product()
            if not product or not item.pricelist_id:
                continue
            company = item.pricelist_id.company_id or self.env.company
            product = product.with_company(company)
            item.reza_sale_price = product.lst_price
            item.reza_rule_price = item.with_company(company)._compute_price(
                product, 1.0, product.uom_id, date=now)
            item.reza_in_use = item.id in in_use
            if item.reza_sale_price:
                item.reza_off_pct = 1 - item.reza_rule_price / item.reza_sale_price

    @api.depends("compute_price", "fixed_price", "percent_price", "base", "base_pricelist_id",
                 "price_discount", "price_surcharge")
    def _compute_reza_rule_text(self):
        for item in self:
            item.reza_rule_text = item._reza_rule_text()
            if item.compute_price == "fixed":
                item.reza_kind = "fixed"
            elif item.compute_price == "formula":
                item.reza_kind = "formula"
            else:
                item.reza_kind = "pct" if item.percent_price else "full"

    def _reza_rule_text(self):
        """The rule in words, e.g. "Fixed price $8.00" or "25% off normal price"."""
        if not self:
            return ""
        self.ensure_one()
        if self.base == "pricelist" and self.base_pricelist_id:
            base = "%s price" % self.base_pricelist_id.name
        elif self.base == "standard_price":
            base = "cost"
        else:
            base = "normal price"
        if self.compute_price == "fixed":
            return "Fixed price $%.2f" % self.fixed_price
        if self.compute_price == "percentage":
            if not self.percent_price:
                return "No discount (%s)" % base
            return "%g%% off %s" % (self.percent_price, base)
        text = "Formula on %s" % base
        if self.price_discount:
            text += ", %g%% off" % self.price_discount
        if self.price_surcharge:
            text += ", %s$%.2f" % ("+" if self.price_surcharge > 0 else "-", abs(self.price_surcharge))
        return text

    def _reza_scope_text(self):
        """Which level the rule sits at, short enough for a list column."""
        self.ensure_one()
        if self.applied_on == "0_product_variant":
            return "Variant rule"
        if self.applied_on == "1_product":
            return "Product rule"
        if self.applied_on == "2_product_category":
            return "Category rule (%s)" % (self.categ_id.name or "")
        return "All-products rule"

    @api.depends("date_start", "date_end")
    def _compute_reza_dates(self):
        now = fields.Datetime.now()
        for item in self:
            start, end = item.date_start, item.date_end
            item.reza_dates_text = item._reza_dates_text()
            if not start and not end:
                item.reza_date_state = "always"
            elif end and end < now:
                item.reza_date_state = "expired"
            elif start and start > now:
                item.reza_date_state = "future"
            else:
                item.reza_date_state = "running"

    def _reza_dates_text(self):
        """The rule's dates in the user's own time zone."""
        if not self:
            return ""
        self.ensure_one()

        def day(value):
            return fields.Datetime.context_timestamp(self, value).strftime("%d/%m/%Y")

        if self.date_start and self.date_end:
            return "%s to %s" % (day(self.date_start), day(self.date_end))
        if self.date_start:
            return "From %s" % day(self.date_start)
        if self.date_end:
            return "Until %s" % day(self.date_end)
        return ""

    def _reza_sample_product(self):
        """The product a product/variant rule prices, or nothing.

        A rule on a parent with several variants prices each variant; the
        first one stands in for the row, which is exact unless a colour or
        size carries a price_extra.
        """
        if self.applied_on == "0_product_variant":
            return self.product_id
        if self.applied_on == "1_product":
            return self.product_tmpl_id.product_variant_ids[:1]
        return self.env["product.product"]
