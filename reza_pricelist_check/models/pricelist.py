# -*- coding: utf-8 -*-
from odoo import _, models

# Context key carrying the check's rule cache (see _reza_cached_rules).
REPORT_RULES_KEY = "reza_pricelist_check_rules"


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    def action_reza_check_prices(self, mode=None):
        self.ensure_one()
        check = self.env["reza.pricelist.check"].create({
            "pricelist_id": self.id,
            "company_id": (self.company_id or self.env.company).id,
        })
        check._reza_run()
        return check.action_open_lines(mode)

    def action_reza_not_discounted(self):
        """Products no rule on this list touches, so they sell at normal price."""
        return self.action_reza_check_prices("no_rule")

    def action_reza_not_allowed_discount(self):
        """Products a rule on this list deliberately holds at normal price."""
        return self.action_reza_check_prices("same")

    def action_reza_conflicts(self):
        """Products two or more rules on this list disagree about."""
        return self.action_reza_check_prices("conflict")

    def action_reza_open_rules(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "reza_pricelist_check.action_reza_price_rules")
        action["name"] = _("Rules: %s", self.name)
        action["domain"] = [("pricelist_id", "=", self.id)]
        action["context"] = {
            "default_pricelist_id": self.id,
            "reza_one_pricelist": True,
            "search_default_current": 1,
            "search_default_groupby_applied_on": 1,
            "search_default_groupby_reza_category": 1,
        }
        return action

    # --- One rule search per list while a check runs -------------------------
    #
    # Pricing every product one by one runs one rule search per product. While
    # a check runs (context key above) the rules are fetched ONCE per list for
    # the whole product set, and each single-product call gets the slice its
    # own search would have returned, in the same order. Outside a check this
    # changes nothing.

    def _get_applicable_rules(self, products, date, **kwargs):
        rules = self._reza_cached_rules(products, date, **kwargs)
        if rules is not None:
            return rules
        return super()._get_applicable_rules(products, date, **kwargs)

    def _reza_cached_rules(self, products, date, **kwargs):
        """The rules core's search would return for one product, or None."""
        state = self.env.context.get(REPORT_RULES_KEY)
        if (
            not state
            or not self
            or kwargs
            or not date
            or len(products) != 1
            or products.id not in state["ids"].get(products._name, ())
        ):
            return None
        product = products
        categ = product.sudo().categ_id
        if not categ:
            return None

        key = (
            self.id,
            product._name,
            date,
            self.env.uid,
            self.env.su,
            tuple(self.env.context.get("allowed_company_ids") or ()),
        )
        index = state["rules"].get(key)
        if index is None:
            index = state["rules"][key] = self._reza_rule_index(
                self.env[product._name].browse(state["ids"][product._name]), date
            )

        is_template = product._name == "product.template"
        tmpl_id = product.id if is_template else product.product_tmpl_id.id
        ancestors = {int(x) for x in categ.parent_path.split("/") if x}
        candidates = (
            index["by_product"].get(product.id, [])
            + index["by_tmpl"].get(tmpl_id, [])
            + [rec for c in ancestors for rec in index["by_categ"].get(c, [])]
            + index["global"]
        )
        picked = []
        for pos, rule_id, r_categ, r_tmpl, r_prod, r_prod_tmpl in candidates:
            if r_categ and r_categ not in ancestors:
                continue
            if r_tmpl and r_tmpl != tmpl_id:
                continue
            if r_prod and (r_prod_tmpl if is_template else r_prod) != product.id:
                continue
            picked.append((pos, rule_id))
        picked.sort()
        Item = self.env["product.pricelist.item"]
        return Item.browse([rule_id for _pos, rule_id in picked]).with_prefetch(index["ids"])

    def _reza_rule_index(self, products, date):
        """One rule search for the whole product set, indexed for slicing."""
        # Same search as core's _get_applicable_rules, archived rules included.
        rules = self.env["product.pricelist.item"].with_context(active_test=False).search(
            self._get_applicable_rules_domain(products=products, date=date)
        ).with_context(self.env.context)
        index = {"ids": tuple(rules.ids), "by_product": {}, "by_tmpl": {}, "by_categ": {}, "global": []}
        by_template = products._name == "product.template"
        for pos, rule in enumerate(rules.sudo()):
            rec = (
                pos,
                rule.id,
                rule.categ_id.id,
                rule.product_tmpl_id.id,
                rule.product_id.id,
                rule.product_id.product_tmpl_id.id,
            )
            if rule.product_id:
                bucket_key = rec[5] if by_template else rec[4]
                index["by_product"].setdefault(bucket_key, []).append(rec)
            elif rule.product_tmpl_id:
                index["by_tmpl"].setdefault(rec[3], []).append(rec)
            elif rule.categ_id:
                index["by_categ"].setdefault(rec[2], []).append(rec)
            else:
                index["global"].append(rec)
        return index
