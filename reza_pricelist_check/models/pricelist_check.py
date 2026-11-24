# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .pricelist import REPORT_RULES_KEY

# A price within half a cent of another counts as the same price.
TOLERANCE = 0.005

STATUS = [
    ("discount", "Discounted"),
    ("same", "Not allowed a discount"),
    ("no_rule", "Not discounted"),
    ("above", "Above sale"),
    ("zero", "Zero price"),
    ("below_cost", "Below cost"),
]


class PricelistCheck(models.TransientModel):
    """One run of Check Prices: every sellable product priced on one list.

    Kept as transient rows (not a SQL view) because the price comes from the
    pricing engine, not from a column: chained lists, rounding and margins
    can only be answered by asking the list itself.
    """

    _name = "reza.pricelist.check"
    _description = "Price List Check"
    # A person may leave the screen open while they fix rules; the rows must
    # outlive the default one-hour vacuum, and the lines must match it.
    _transient_max_hours = 12.0

    pricelist_id = fields.Many2one("product.pricelist", required=True, readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    checked_at = fields.Datetime(readonly=True)
    line_ids = fields.One2many("reza.pricelist.check.line", "check_id")

    @api.depends("pricelist_id", "checked_at")
    def _compute_display_name(self):
        for check in self:
            check.display_name = _("Check: %s", check.pricelist_id.display_name)

    def _reza_products(self):
        """Every active sellable goods variant this list's company can sell.

        A branch (e.g. Rockos under Ecom Superstore) can sell its parent
        company's products, so the parents count too.
        """
        domain = [("sale_ok", "=", True), ("type", "=", "consu")]
        company = self.pricelist_id.company_id
        if company:
            domain += ["|", ("company_id", "=", False), ("company_id", "in", company.parent_ids.ids)]
        return self.env["product.product"].search(domain, order="default_code, id")

    def _reza_engine(self, products):
        """The list, primed so each product's rule search is a cache slice."""
        company = self.pricelist_id.company_id or self.env.company
        state = {
            "date": fields.Datetime.now(),
            "ids": {"product.product": frozenset(products.ids)},
            "rules": {},
        }
        return self.pricelist_id.with_company(company).with_context(**{REPORT_RULES_KEY: state}), state

    def _reza_run(self, products=None):
        """Price every sellable product on this list, or only `products`.

        The product page passes its own variants, so asking "which lists
        price this product" costs a handful of rows per list, not a whole
        catalogue per list.
        """
        self.ensure_one()
        company = self.pricelist_id.company_id or self.env.company
        if products is None:
            products = self._reza_products()
        products = products.with_company(company)
        engine, state = self._reza_engine(products)
        vals_list = [dict(self._reza_row(engine, state["date"], product), check_id=self.id,
                          pricelist_id=self.pricelist_id.id)
                     for product in products]
        self.env["reza.pricelist.check.line"].create(vals_list)
        self.checked_at = state["date"]

    def _reza_row(self, engine, date, product):
        """Everything a row says about one product on this list."""
        Item = self.env["product.pricelist.item"]
        price, rule_id = engine._get_product_price_rule(product, 1.0, date=date)
        rule = Item.browse(rule_id)
        base_rule = Item
        if rule and rule.base == "pricelist" and rule.base_pricelist_id:
            base = rule.base_pricelist_id.with_company(engine.env.company).with_context(engine.env.context)
            base_rule = Item.browse(base._get_product_price_rule(product, 1.0, date=date)[1])
        sale = product.lst_price
        cost = product.standard_price
        conflict, conflict_text, match_count = self._reza_conflicts(engine, date, product, rule, price)
        return {
            "product_id": product.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "default_code": product.default_code,
            "categ_id": product.categ_id.id,
            "difference": price - sale,
            "discount_pct": (1 - price / sale) if sale else 0.0,
            "sale_price": sale,
            "cost": cost,
            "price": price,
            "rule_id": rule.id or False,
            "rule_applied_on": rule.applied_on or False,
            "base_rule_id": base_rule.id or False,
            "status": self._reza_status(price, sale, rule.id, cost),
            "why": self._reza_why(rule, base_rule),
            "conflict": conflict,
            "conflict_text": conflict_text,
            "match_count": match_count,
        }

    def _reza_conflicts(self, engine, date, product, winner, price):
        """Every other rule on the list that also matches this product.

        Uses the same ordered rule list and the same applicability test as
        the pricing engine (product.pricelist._compute_price_rule), so the
        first match IS the winner and the rest are the rules it beat.
        Returns (conflict, text, number of matching rules).
        """
        rules = engine._get_applicable_rules(product, 1.0, date)
        matching = [r for r in rules if r._is_applicable_for(product, 1.0)]
        losers = [r for r in matching if r != winner]
        if not losers:
            return "none", False, len(matching)
        parts, differs = [], False
        for loser in losers:
            other = loser._compute_price(product, 1.0, product.uom_id, date=date,
                                         currency=engine.currency_id)
            if abs(other - price) > TOLERANCE:
                differs = True
            parts.append("%s: %s would charge $%.2f (%s)" % (
                loser._reza_scope_text(), loser._reza_rule_text(), other,
                self._reza_beats(winner, loser)))
        return ("conflict" if differs else "overlap"), "; ".join(parts), len(matching)

    @staticmethod
    def _reza_beats(winner, loser):
        """Why the winner was picked over the loser, in words."""
        levels = {"0_product_variant": "variant", "1_product": "product",
                  "2_product_category": "category", "3_global": "all-products"}
        if winner.applied_on != loser.applied_on:
            return "loses: a %s rule beats a %s rule" % (
                levels[winner.applied_on], levels[loser.applied_on])
        if winner.min_quantity != loser.min_quantity:
            return "loses: the rule with the higher minimum quantity is checked first"
        if winner.applied_on == "2_product_category":
            return "loses: both are category rules and %s is checked first" % winner.categ_id.name
        return "loses: two rules on the same item, the newer one wins"

    @staticmethod
    def _reza_why(rule, base_rule):
        if not rule:
            return "No rule on this list, so the normal price"
        why = "%s: %s" % (rule._reza_scope_text(), rule._reza_rule_text())
        if rule._reza_dates_text():
            why += ", %s" % rule._reza_dates_text()
        if base_rule:
            why += ", where %s has %s: %s" % (
                rule.base_pricelist_id.name, base_rule._reza_scope_text().lower(),
                base_rule._reza_rule_text())
        return why

    @staticmethod
    def _reza_status(price, sale, rule_id, cost=0.0):
        if price <= TOLERANCE:
            return "zero"
        if cost > TOLERANCE and price < cost - TOLERANCE:
            return "below_cost"
        if price > sale + TOLERANCE:
            return "above"
        if not rule_id:
            return "no_rule"
        if abs(price - sale) <= TOLERANCE:
            return "same"
        return "discount"

    def action_open_lines(self, mode=None):
        self.ensure_one()
        titles = {
            None: _("Check Prices: %s", self.pricelist_id.name),
            "no_rule": _("Not Discounted: %s", self.pricelist_id.name),
            "same": _("Not Allowed a Discount: %s", self.pricelist_id.name),
            "conflict": _("Conflicting Discounts: %s", self.pricelist_id.name),
        }
        context = {"search_default_groupby_status": 1}
        if mode == "conflict":
            context = {"search_default_conflicts": 1, "search_default_groupby_categ": 1}
        elif mode:
            context = {"search_default_status_%s" % mode: 1, "search_default_groupby_categ": 1}
        return {
            "type": "ir.actions.act_window",
            "name": titles[mode],
            "res_model": "reza.pricelist.check.line",
            "view_mode": "list,form",
            "domain": [("check_id", "=", self.id)],
            "context": context,
            "target": "current",
        }


class PricelistCheckLine(models.TransientModel):
    _name = "reza.pricelist.check.line"
    _description = "Price List Check Row"
    _order = "default_code, id"
    _transient_max_hours = 12.0

    check_id = fields.Many2one("reza.pricelist.check", required=True, ondelete="cascade", index=True)
    # Written once at the run (not related) so the product page can group,
    # filter and sort its rows by list.
    pricelist_id = fields.Many2one("product.pricelist", string="Price List", readonly=True,
                                   index=True)
    pricelist_company_id = fields.Many2one(related="pricelist_id.company_id",
                                           string="List Company")
    pricelist_website_id = fields.Many2one(related="pricelist_id.website_id",
                                           string="Website")
    product_id = fields.Many2one("product.product", string="Product", required=True, readonly=True)
    # Plain columns written once at the run, not related fields: a related
    # store would issue a second UPDATE over every row straight after insert.
    product_tmpl_id = fields.Many2one("product.template", string="Parent Product", readonly=True)
    default_code = fields.Char(string="SKU", readonly=True)
    categ_id = fields.Many2one("product.category", string="Category", readonly=True)
    currency_id = fields.Many2one(related="pricelist_id.currency_id")
    sale_price = fields.Monetary(string="Normal Price", readonly=True, aggregator=False,
                                 help="The Sale Price on the product, before any list.")
    price = fields.Monetary(string="This List Charges", readonly=True, aggregator=False,
                            help="What this list charges for one unit today.")
    discount_pct = fields.Float(string="% Off", readonly=True, aggregator=False)
    difference = fields.Monetary(string="Difference", readonly=True, aggregator=False,
                                 help="This List Charges less Normal Price. Negative is a discount.")
    cost = fields.Monetary(
        string="Cost", readonly=True, aggregator=False, groups="sales_team.group_sale_manager",
        help="The product cost in the list's company when the check ran.")
    rule_id = fields.Many2one("product.pricelist.item", string="Rule Used", readonly=True,
                              ondelete="set null")
    rule_applied_on = fields.Selection(
        [("3_global", "All Products"), ("2_product_category", "Product Category"),
         ("1_product", "Product"), ("0_product_variant", "Product Variant")],
        string="Rule Level", readonly=True)
    rule_price = fields.Char(related="rule_id.price", string="Rule")
    base_rule_id = fields.Many2one(
        "product.pricelist.item", string="Underlying Rule", readonly=True, ondelete="set null",
        help="For a list priced off another list, the rule that other list used.")
    status = fields.Selection(STATUS, readonly=True)
    why = fields.Char(string="Why", readonly=True,
                      help="Which rule set the price, in words.")
    conflict = fields.Selection(
        [("none", "No"), ("overlap", "Overlap, same price"), ("conflict", "Conflict")],
        string="Other Rules", readonly=True,
        help="Conflict: another rule on this list also matches and would "
             "charge a different price. The rule in Why wins.")
    conflict_text = fields.Char(string="Rules It Beat", readonly=True)
    match_count = fields.Integer(string="Matching Rules", readonly=True, aggregator=False)

    def _reza_refresh(self):
        """Re-price these rows after their rules changed."""
        for check in self.mapped("check_id"):
            rows = self.filtered(lambda l: l.check_id == check)
            company = check.pricelist_id.company_id or self.env.company
            products = rows.mapped("product_id").with_company(company)
            engine, state = check._reza_engine(products)
            by_product = {p.id: p for p in products}
            for row in rows:
                row.write(check._reza_row(engine, state["date"], by_product[row.product_id.id]))

    def _reza_zero_rules(self, row):
        """This list's 0% rules aimed at exactly this product or variant."""
        return self.env["product.pricelist.item"].search([
            ("pricelist_id", "=", row.pricelist_id.id),
            ("compute_price", "=", "discount"), ("price_discount", "=", 0),
            ("price_round", "=", 0), ("price_surcharge", "=", 0),
            ("price_min_margin", "=", 0), ("price_max_margin", "=", 0),
            ("base", "=", "list_price"),
            "|", "&", ("applied_on", "=", "0_product_variant"), ("product_id", "=", row.product_id.id),
            "&", ("applied_on", "=", "1_product"), ("product_tmpl_id", "=", row.product_tmpl_id.id),
        ])

    def action_reza_exclude(self):
        """Keep these products at the normal price on this list.

        Adds one 0% variant rule per product. A variant rule beats product,
        category and all-product rules, and among variant rules for the same
        item the newest wins, so the new rule is the one used. Existing rules
        are left alone; they show as Not in use under Price Rules.
        """
        Item = self.env["product.pricelist.item"]
        for row in self:
            if row.status == "same" and row.rule_id in self._reza_zero_rules(row):
                continue
            Item.create({
                "pricelist_id": row.pricelist_id.id,
                "applied_on": "0_product_variant",
                "product_id": row.product_id.id,
                "product_tmpl_id": row.product_tmpl_id.id,
                "compute_price": "discount",
                "price_discount": 0.0,
                "base": "list_price",
            })
        self._reza_refresh()
        return self._reza_reload()

    def action_reza_allow(self):
        """Undo Exclude: remove this list's 0% rules aimed at these products."""
        for row in self:
            self._reza_zero_rules(row).unlink()
        self._reza_refresh()
        return self._reza_reload()

    def _reza_reload(self):
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_open_rule(self):
        self.ensure_one()
        rule = self.rule_id
        if not rule:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "product.pricelist.item",
            "res_id": rule.id,
            "view_mode": "form",
            "target": "new",
        }
