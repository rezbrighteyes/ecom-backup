from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPricelistCheck(TransactionCase):
    """Check Prices must say what the list really charges, and why."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categ = cls.env["product.category"].create({"name": "Check Test Eyewear"})
        cls.other_categ = cls.env["product.category"].create({"name": "Check Test Footwear"})
        cls.discounted = cls._product("Check Discounted", cls.categ, 20.0)
        cls.missed = cls._product("Check Missed", cls.other_categ, 10.0)
        cls.fixed = cls._product("Check Fixed Above", cls.other_categ, 10.0)
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Check Test List",
            "company_id": False,
            "item_ids": [
                (0, 0, {"applied_on": "2_product_category", "categ_id": cls.categ.id,
                        "compute_price": "percentage", "percent_price": 25.0}),
                (0, 0, {"applied_on": "0_product_variant", "product_id": cls.fixed.id,
                        "product_tmpl_id": cls.fixed.product_tmpl_id.id,
                        "compute_price": "fixed", "fixed_price": 12.0}),
            ],
        })

    @classmethod
    def _product(cls, name, categ, price):
        return cls.env["product.product"].create({
            "name": name, "type": "consu", "sale_ok": True,
            "categ_id": categ.id, "list_price": price,
        })

    def _run(self):
        action = self.pricelist.action_reza_check_prices()
        return self.env["reza.pricelist.check.line"].search(action["domain"])

    def test_each_product_gets_the_right_status(self):
        lines = self._run()
        by_product = {l.product_id: l for l in lines}
        disc = by_product[self.discounted]
        self.assertEqual(disc.status, "discount")
        self.assertAlmostEqual(disc.price, 15.0)
        self.assertAlmostEqual(disc.discount_pct, 0.25)
        self.assertEqual(disc.rule_applied_on, "2_product_category")
        missed = by_product[self.missed]
        self.assertEqual(missed.status, "no_rule")
        self.assertFalse(missed.rule_id)
        self.assertAlmostEqual(missed.price, 10.0)
        self.assertEqual(by_product[self.fixed].status, "above")

    def test_status_rules(self):
        status = self.env["reza.pricelist.check"]._reza_status
        self.assertEqual(status(0.0, 10.0, 5), "zero")
        self.assertEqual(status(10.0, 10.0, 5), "same")
        self.assertEqual(status(10.0, 10.0, False), "no_rule")
        self.assertEqual(status(9.0, 10.0, 5), "discount")
        self.assertEqual(status(11.0, 10.0, 5), "above")

    def test_rule_list_shows_what_a_rule_works_out_at(self):
        rule = self.pricelist.item_ids.filtered(lambda r: r.applied_on == "0_product_variant")
        self.assertAlmostEqual(rule.reza_rule_price, 12.0)
        self.assertAlmostEqual(rule.reza_sale_price, 10.0)
        self.assertTrue(rule.reza_in_use)
        self.assertEqual(rule.reza_category_id, self.other_categ)
        categ_rule = self.pricelist.item_ids - rule
        self.assertEqual(categ_rule.reza_category_id, self.categ)
        self.assertFalse(categ_rule.reza_in_use)

    def test_a_shadowed_rule_is_not_in_use(self):
        # A second variant rule for the same product: core picks the newer
        # (id desc), so the older one changes nothing.
        old = self.pricelist.item_ids.filtered(lambda r: r.applied_on == "0_product_variant")
        new = self.env["product.pricelist.item"].create({
            "pricelist_id": self.pricelist.id, "applied_on": "0_product_variant",
            "product_id": self.fixed.id, "product_tmpl_id": self.fixed.product_tmpl_id.id,
            "compute_price": "fixed", "fixed_price": 8.0,
        })
        self.assertTrue(new.reza_in_use)
        old.invalidate_recordset(["reza_in_use"])
        self.assertFalse(old.reza_in_use)

    def test_only_own_runs_are_visible(self):
        self._run()
        other = self.env["res.users"].create({
            "name": "Check Other", "login": "check.other.user",
            "groups_id": [(6, 0, [self.env.ref("sales_team.group_sale_salesman").id,
                                   self.env.ref("base.group_user").id])],
        })
        self.env.invalidate_all()
        self.assertFalse(self.env["reza.pricelist.check.line"].with_user(other).search([]))

    def test_rules_and_reasons_read_in_plain_words(self):
        categ_rule = self.pricelist.item_ids.filtered(lambda r: r.applied_on == "2_product_category")
        fixed_rule = self.pricelist.item_ids - categ_rule
        self.assertEqual(categ_rule.reza_rule_text, "25% off normal price")
        self.assertEqual(categ_rule.reza_kind, "pct")
        self.assertEqual(fixed_rule.reza_kind, "fixed")
        self.assertEqual(fixed_rule.reza_rule_text, "Fixed price $12.00")
        self.assertAlmostEqual(fixed_rule.reza_off_pct, -0.2)
        by_product = {l.product_id: l for l in self._run()}
        self.assertEqual(by_product[self.discounted].why,
                         "Category rule (Check Test Eyewear): 25% off normal price")
        self.assertEqual(by_product[self.missed].why, "No rule on this list, so the normal price")

    def test_dates_say_whether_a_rule_is_running(self):
        from datetime import timedelta
        from odoo import fields
        rule = self.pricelist.item_ids.filtered(lambda r: r.applied_on == "2_product_category")
        self.assertEqual(rule.reza_date_state, "always")
        now = fields.Datetime.now()
        rule.write({"date_start": now - timedelta(days=30), "date_end": now - timedelta(days=1)})
        self.assertEqual(rule.reza_date_state, "expired")
        self.assertIn(" to ", rule.reza_dates_text)
        rule.write({"date_end": now + timedelta(days=5)})
        self.assertEqual(rule.reza_date_state, "running")
        rule.write({"date_start": now + timedelta(days=1)})
        self.assertEqual(rule.reza_date_state, "future")

    def test_the_two_shortcut_buttons_open_the_right_rows(self):
        excluded = self._product("Check Excluded", self.categ, 30.0)
        self.env["product.pricelist.item"].create({
            "pricelist_id": self.pricelist.id, "applied_on": "0_product_variant",
            "product_id": excluded.id, "product_tmpl_id": excluded.product_tmpl_id.id,
            "compute_price": "percentage", "percent_price": 0.0,
        })
        Line = self.env["reza.pricelist.check.line"]
        action = self.pricelist.action_reza_not_discounted()
        self.assertEqual(action["context"].get("search_default_status_no_rule"), 1)
        lines = {l.product_id: l.status for l in Line.search(action["domain"])}
        self.assertEqual(lines[self.missed], "no_rule")
        self.assertEqual(lines[excluded], "same")
        action = self.pricelist.action_reza_not_allowed_discount()
        self.assertEqual(action["context"].get("search_default_status_same"), 1)

    def test_a_price_below_cost_is_flagged(self):
        status = self.env["reza.pricelist.check"]._reza_status
        self.assertEqual(status(9.0, 20.0, 5, 10.0), "below_cost")
        self.assertEqual(status(11.0, 20.0, 5, 10.0), "discount")
        self.assertEqual(status(9.0, 20.0, 5, 0.0), "discount")
        self.discounted.standard_price = 16.0
        by_product = {l.product_id: l for l in self._run()}
        self.assertEqual(by_product[self.discounted].status, "below_cost")

    def test_not_in_use_can_be_searched(self):
        old = self.pricelist.item_ids.filtered(lambda r: r.applied_on == "0_product_variant")
        new = self.env["product.pricelist.item"].create({
            "pricelist_id": self.pricelist.id, "applied_on": "0_product_variant",
            "product_id": self.fixed.id, "product_tmpl_id": self.fixed.product_tmpl_id.id,
            "compute_price": "fixed", "fixed_price": 8.0,
        })
        Item = self.env["product.pricelist.item"]
        mine = [("pricelist_id", "=", self.pricelist.id)]
        self.assertEqual(Item.search(mine + [("reza_in_use", "=", False),
                                             ("applied_on", "=", "0_product_variant")]), old)
        self.assertEqual(Item.search(mine + [("reza_in_use", "=", True)]), new)

    def test_customer_button_opens_their_list(self):
        partner = self.env["res.partner"].create({"name": "Check Customer"})
        partner.with_company(self.env.company).property_product_pricelist = self.pricelist
        action = partner.action_reza_check_prices()
        line = self.env["reza.pricelist.check.line"].search(action["domain"], limit=1)
        self.assertEqual(line.pricelist_id, self.pricelist)

    def test_a_conflict_names_the_winner_and_the_loser(self):
        # A 10% product rule on a product the 25% category rule also covers.
        self.env["product.pricelist.item"].create({
            "pricelist_id": self.pricelist.id, "applied_on": "1_product",
            "product_tmpl_id": self.discounted.product_tmpl_id.id,
            "compute_price": "percentage", "percent_price": 10.0,
        })
        line = {l.product_id: l for l in self._run()}[self.discounted]
        self.assertEqual(line.conflict, "conflict")
        self.assertEqual(line.match_count, 2)
        self.assertAlmostEqual(line.price, 18.0)
        self.assertIn("Product rule: 10% off", line.why)
        self.assertIn("25% off normal price would charge $15.00", line.conflict_text)
        self.assertIn("a product rule beats a category rule", line.conflict_text)
        missed = {l.product_id: l for l in self._run()}[self.missed]
        self.assertEqual(missed.conflict, "none")

    def test_exclude_then_allow_again(self):
        line = {l.product_id: l for l in self._run()}[self.discounted]
        self.assertEqual(line.status, "discount")
        line.action_reza_exclude()
        self.assertEqual(line.status, "same")
        self.assertAlmostEqual(line.price, 20.0)
        self.assertEqual(line.rule_applied_on, "0_product_variant")
        line.action_reza_exclude()  # twice must not stack a second rule
        rules = self.pricelist.item_ids.filtered(lambda r: r.product_id == self.discounted)
        self.assertEqual(len(rules), 1)
        line.action_reza_allow()
        self.assertEqual(line.status, "discount")
        self.assertAlmostEqual(line.price, 15.0)
        self.assertFalse(self.pricelist.item_ids.filtered(lambda r: r.product_id == self.discounted))

    # Price Lists on the product: the reverse of Check Prices.

    def _by_product(self, product):
        action = product.action_reza_price_lists()
        lines = self.env["reza.pricelist.check.line"].search(action["domain"])
        return action, {l.pricelist_id: l for l in lines}

    def test_product_page_finds_a_list_that_only_has_a_category_rule(self):
        # No rule on the test list names this product: only its category does.
        _action, rows = self._by_product(self.discounted)
        row = rows[self.pricelist]
        self.assertEqual(row.product_id, self.discounted)
        self.assertEqual(row.rule_applied_on, "2_product_category")
        self.assertAlmostEqual(row.price, 15.0)
        self.assertEqual(row.status, "discount")

    def test_product_page_lists_every_list_once_and_only_this_product(self):
        action, rows = self._by_product(self.missed)
        lines = self.env["reza.pricelist.check.line"].search(action["domain"])
        self.assertEqual(set(lines.mapped("product_id")), {self.missed})
        self.assertEqual(len(lines), len(rows), "one row per list")
        self.assertIn(self.pricelist, rows)
        self.assertEqual(rows[self.pricelist].status, "no_rule")
        self.assertEqual(len(rows), len(self.missed._reza_price_list_scope()))

    def test_product_page_agrees_with_check_prices(self):
        list_side = {l.product_id: l for l in self._run()}
        for product in (self.discounted, self.missed, self.fixed):
            _action, rows = self._by_product(product)
            a, b = list_side[product], rows[self.pricelist]
            self.assertAlmostEqual(a.price, b.price)
            self.assertEqual(a.status, b.status)
            self.assertEqual(a.rule_id, b.rule_id)

    def test_a_product_held_by_one_company_skips_other_companies_lists(self):
        family = self.env["res.company"].search([("id", "child_of", self.env.company.id)])
        other = self.env["res.company"].search(
            [("id", "not in", (family | self.env.company.parent_ids).ids)], limit=1)
        if not other:
            other = self.env["res.company"].create({"name": "Check Other Company"})
        foreign = self.env["product.pricelist"].create({"name": "Check Foreign", "company_id": other.id})
        self.missed.product_tmpl_id.company_id = self.env.company
        _action, rows = self._by_product(self.missed)
        self.assertNotIn(foreign, rows)
        self.assertIn(self.pricelist, rows, "a list with no company is still offered")

    def test_template_button_covers_every_variant(self):
        action = self.missed.product_tmpl_id.action_reza_price_lists()
        lines = self.env["reza.pricelist.check.line"].search(action["domain"])
        self.assertEqual(lines.mapped("product_id"), self.missed.product_tmpl_id.product_variant_ids)

    def test_a_branch_list_checks_its_parent_companys_products(self):
        # Rockos is a branch of Ecom Superstore: its lists sell the parent's range.
        parent = self.env.company
        branch = self.env["res.company"].create({"name": "Check Branch", "parent_id": parent.id})
        self.missed.product_tmpl_id.company_id = parent
        branch_list = self.env["product.pricelist"].create({"name": "Check Branch List", "company_id": branch.id})
        self.assertIn(branch_list, self.missed._reza_price_list_scope())
        check = self.env["reza.pricelist.check"].create({"pricelist_id": branch_list.id, "company_id": branch.id})
        self.assertIn(self.missed, check._reza_products())

    def test_the_cache_returns_the_same_rules_as_core(self):
        # The one-search-per-list cache must hand back exactly what core would.
        from odoo import fields
        from odoo.addons.reza_pricelist_check.models.pricelist import REPORT_RULES_KEY
        self.env["product.pricelist.item"].create({
            "pricelist_id": self.pricelist.id, "applied_on": "1_product",
            "product_tmpl_id": self.discounted.product_tmpl_id.id,
            "compute_price": "percentage", "percent_price": 10.0,
        })
        self.env["product.pricelist.item"].create({
            "pricelist_id": self.pricelist.id, "applied_on": "3_global",
            "compute_price": "percentage", "percent_price": 5.0,
        })
        now = fields.Datetime.now()
        products = self.discounted | self.missed | self.fixed
        state = {"date": now, "ids": {"product.product": frozenset(products.ids)}, "rules": {}}
        cached = self.pricelist.with_context(**{REPORT_RULES_KEY: state})
        for product in products:
            self.assertEqual(cached._get_applicable_rules(product, now),
                             self.pricelist._get_applicable_rules(product, now))
            self.assertEqual(cached._get_product_price_rule(product, 1.0, date=now),
                             self.pricelist._get_product_price_rule(product, 1.0, date=now))
