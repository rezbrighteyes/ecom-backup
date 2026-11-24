# -*- coding: utf-8 -*-
"""Tests for the Edbert stock figures shown on ecom products.

The wholesale database is replaced by a fake, so no test reaches the network.
The fake answers the three reads the sync makes and records them, which is what
lets a test assert that a refusal happened BEFORE anything was written.
"""

import logging

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

_logger = logging.getLogger(__name__)

SYNC = "reza.edbert.stock.sync"
LOCATION = 8


class FakeWholesale:
    """Stands in for the wholesale database.

    Holds one internal location, a set of quants and a product catalogue. A
    product absent from `products` is one that no longer exists in wholesale,
    which is the state 5,374 of the real mappings are in.
    """

    def __init__(self, quants=None, products=None, locations=None):
        self.locations = (
            locations
            if locations is not None
            else [
                {
                    "id": LOCATION,
                    "complete_name": "WH/Stock",
                    "usage": "internal",
                    "company_id": (1, "Edbert Holdings Pty Ltd"),
                }
            ]
        )
        self.quants = quants if quants is not None else []
        # A value may be a plain reference or a dict of identifier fields, so
        # that a test can give a product a barcode that differs from its
        # reference -- which is the ordinary shape across these two catalogues.
        self.products = {
            pid: (value if isinstance(value, dict) else {"default_code": value})
            for pid, value in (products or {}).items()
        }
        self.calls = []
        self.fields_asked = set()
        self.quant_domain = None

    @staticmethod
    def _leaf(domain, field):
        for leaf in domain:
            if isinstance(leaf, (list, tuple)) and leaf[0] == field:
                return leaf[1], leaf[2]
        return None, None

    def __call__(self, model, method, args, kwargs=None):
        self.calls.append((model, method))
        domain = args[0]
        if model == "stock.location":
            _op, value = self._leaf(domain, "id")
            return [row for row in self.locations if row["id"] == value]
        if model == "stock.quant":
            self.quant_domain = list(domain)
            _op, value = self._leaf(domain, "location_id")
            return [row for row in self.quants if row["location_id"] == value]
        if model == "product.product":
            _op, value = self._leaf(domain, "id")
            wanted = set(value or [])
            asked = list((kwargs or {}).get("fields") or [])
            self.fields_asked.update(asked)
            return [
                dict({field: row.get(field, False) for field in asked}, id=pid)
                for pid, row in self.products.items()
                if pid in wanted
            ]
        raise AssertionError("the sync read an unexpected model: %s" % model)


def quant(product_id, quantity, reserved=0.0):
    return {
        "location_id": LOCATION,
        "product_id": (product_id, "wholesale product %s" % product_id),
        "quantity": quantity,
        "reserved_quantity": reserved,
    }


@tagged("post_install", "-at_install")
class TestEdbertStockSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync = cls.env[SYNC]

        # The lookup for credentials is exercised for real; only the connection
        # itself is faked, so a company with no credentials still fails loudly.
        cls.env.company.write(
            {
                "external_api": True,
                "external_api_url": "https://example.invalid",
                "external_api_db": "wholesale",
                "external_api_username": "tester",
                "external_api_password": "secret",
            }
        )

        cls.matched = cls._product("REZA-MATCH", 9001)
        cls.zero = cls._product("REZA-ZERO", 9002)
        cls.wrong = cls._product("REZA-WRONG", 9003)
        cls.dead = cls._product("REZA-DEAD", 9004)
        cls.unmapped = cls._product("REZA-NONE", 0)
        cls.all_ids = (
            cls.matched + cls.zero + cls.wrong + cls.dead + cls.unmapped
        )

        # Keep every run to this module's own products. Without it a run reads
        # the whole catalogue, which is right in production and useless here.
        cls.env["ir.config_parameter"].sudo().set_str(
            cls.sync.PARAM_LAST_RESOLVED, 0
        )

    @classmethod
    def _product(cls, code, external_api_id):
        return cls.env["product.product"].create(
            {
                "name": "Edbert stock test %s" % code,
                "default_code": code,
                "external_api_id": external_api_id,
            }
        )

    # ------------------------------------------------------------------
    def _run(self, fake, products=None):
        products = products if products is not None else self.all_ids
        model_class = type(self.env[SYNC])
        self.patch(model_class, "_connect", lambda self, company: fake)
        self.patch(
            model_class,
            "_product_domain",
            lambda self: [("id", "in", products.ids)],
        )
        return self.env[SYNC].run()

    def _fake(self, **kwargs):
        kwargs.setdefault(
            "quants", [quant(9001, 120.0, 20.0), quant(9002, 0.0), quant(9003, 500.0)]
        )
        kwargs.setdefault(
            "products",
            {
                9001: "REZA-MATCH",
                9002: "REZA-ZERO",
                9003: "REZA-SOMETHING-ELSE",
            },
        )
        # The quant floor would otherwise refuse every fixture in this file.
        self.env["ir.config_parameter"].sudo().set_str(self.sync.PARAM_MIN_ROWS, 1)
        return FakeWholesale(**kwargs)

    # ------------------------------------------------------------------
    # What a correct match produces
    # ------------------------------------------------------------------
    def test_matched_product_shows_free_quantity(self):
        """Free quantity is on hand less what is already reserved."""
        self._run(self._fake())
        self.assertEqual(self.matched.reza_edbert_stock_state, "ok")
        self.assertEqual(self.matched.reza_edbert_free_qty, 100.0)
        self.assertFalse(self.matched.reza_edbert_code)
        self.assertTrue(self.matched.reza_edbert_stock_date)

    def test_matched_with_no_stock_is_a_truthful_zero(self):
        """A matched product Edbert holds none of reads zero, not unmatched.

        The two must stay apart. One is a stock question for purchasing, the
        other is a data question for whoever owns the product mapping.
        """
        self._run(self._fake())
        self.assertEqual(self.zero.reza_edbert_stock_state, "ok")
        self.assertEqual(self.zero.reza_edbert_free_qty, 0.0)

    def test_matched_product_absent_from_the_quant_read_reads_zero(self):
        """Edbert reports quants only where it holds stock."""
        fake = self._fake(quants=[quant(9001, 5.0)])
        self._run(fake)
        self.assertEqual(self.zero.reza_edbert_stock_state, "ok")
        self.assertEqual(self.zero.reza_edbert_free_qty, 0.0)

    def test_negative_free_quantity_is_shown_as_zero(self):
        """None of a negative position can be sold, so it is not a figure.

        The third row is positive on purpose. Without it the whole read would
        be zero or less, and the run would refuse before reaching the clamp.
        """
        fake = self._fake(
            quants=[quant(9001, 4.0, 10.0), quant(9002, -30.0), quant(9003, 500.0)]
        )
        self._run(fake)
        self.assertEqual(self.matched.reza_edbert_free_qty, 0.0)
        self.assertEqual(self.zero.reza_edbert_free_qty, 0.0)
        self.assertEqual(self.matched.reza_edbert_stock_state, "ok")

    # ------------------------------------------------------------------
    # The two ways a mapping is wrong
    # ------------------------------------------------------------------
    def test_a_mapping_to_another_product_withholds_the_figure(self):
        """This is the defect that made the code check necessary.

        Measured on production 2026-09-07: 31 ecom products carry an
        external_api_id belonging to an unrelated wholesale product. Showing its
        stock would be worse than showing nothing.
        """
        self._run(self._fake())
        self.assertEqual(self.wrong.reza_edbert_stock_state, "mismatch")
        self.assertEqual(self.wrong.reza_edbert_free_qty, 0.0)
        self.assertEqual(self.wrong.reza_edbert_code, "REZA-SOMETHING-ELSE")

    def test_a_wholesale_product_with_no_reference_cannot_be_verified(self):
        """No reference means the match cannot be proved, so it is withheld."""
        fake = self._fake(products={9001: "REZA-MATCH", 9003: ""})
        self._run(fake)
        self.assertEqual(self.wrong.reza_edbert_stock_state, "mismatch")
        self.assertEqual(self.wrong.reza_edbert_free_qty, 0.0)

    def test_a_differing_reference_is_verified_by_the_barcode(self):
        """The two catalogues label the same product differently.

        Ecom knows Rocko's Tread Thongs size 08 by its EAN and wholesale knows
        it by an internal code, with the EAN in the barcode. Measured on
        production 2026-09-07, all 31 products whose references disagree are
        this shape, and none is a wrong mapping. Refusing them would withhold
        31 correct figures.
        """
        fake = self._fake(
            quants=[quant(9003, 88.0)],
            products={
                9003: {"default_code": "4178Treads08", "barcode": "REZA-WRONG"}
            },
        )
        self._run(fake)
        self.assertEqual(self.wrong.reza_edbert_stock_state, "ok")
        self.assertEqual(self.wrong.reza_edbert_free_qty, 88.0)

    def test_the_model_level_barcode_is_never_read(self):
        """`reza_generic_barcode` is shared by every size of a product.

        Reading it would let size 14 verify against size 08's mapping, so it is
        deliberately left out of the check.
        """
        fake = self._fake()
        self._run(fake)
        self.assertIn("default_code", fake.fields_asked)
        self.assertIn("barcode", fake.fields_asked)
        self.assertNotIn("reza_generic_barcode", fake.fields_asked)

    def test_an_ecom_product_with_no_reference_cannot_be_checked(self):
        """Say "cannot be checked", not "wrong". They need different people."""
        blank = self._product(False, 9001)
        fake = self._fake()
        self._run(fake, products=self.all_ids + blank)
        self.assertEqual(blank.reza_edbert_stock_state, "unverified")
        self.assertEqual(blank.reza_edbert_free_qty, 0.0)

    def test_stray_whitespace_on_either_side_does_not_withhold_a_figure(self):
        """The comparison must weigh like against like.

        Both sides are stripped. Comparing a raw ecom reference against a
        stripped wholesale one would report a correct mapping as a disagreement
        and withhold a real figure. It fails closed, so the cost is a lost
        number rather than a wrong one -- which is exactly why nobody would
        notice.
        """
        # fields.Char trims on write, so the untidy ecom value has to be put
        # there the way an import or a direct load would leave it.
        self.env.cr.execute(
            "UPDATE product_product SET default_code = %s WHERE id = %s",
            ("REZA-MATCH  ", self.matched.id),
        )
        self.matched.invalidate_recordset(["default_code"])
        fake = self._fake(
            quants=[quant(9001, 60.0)],
            products={9001: {"default_code": "  REZA-MATCH "}},
        )
        self._run(fake)
        self.assertEqual(self.matched.reza_edbert_stock_state, "ok")
        self.assertEqual(self.matched.reza_edbert_free_qty, 60.0)

    def test_a_dead_wholesale_id_reports_no_match(self):
        """5,374 stored ids point at products the rebuild deleted."""
        self._run(self._fake())
        self.assertEqual(self.dead.reza_edbert_stock_state, "no_match")
        self.assertEqual(self.dead.reza_edbert_free_qty, 0.0)

    def test_a_product_with_no_mapping_reports_no_match(self):
        self._run(self._fake())
        self.assertEqual(self.unmapped.reza_edbert_stock_state, "no_match")

    def test_a_corrected_mapping_clears_the_mismatch(self):
        """A mismatch must not be sticky once the data is put right."""
        self._run(self._fake())
        self.assertEqual(self.wrong.reza_edbert_stock_state, "mismatch")
        fake = self._fake(
            quants=[quant(9003, 7.0)],
            products={9001: "REZA-MATCH", 9002: "REZA-ZERO", 9003: "REZA-WRONG"},
        )
        self._run(fake)
        self.assertEqual(self.wrong.reza_edbert_stock_state, "ok")
        self.assertEqual(self.wrong.reza_edbert_free_qty, 7.0)
        self.assertFalse(self.wrong.reza_edbert_code)

    # ------------------------------------------------------------------
    # Refusals. Each one must leave the figures untouched.
    # ------------------------------------------------------------------
    def test_a_short_stock_read_is_refused(self):
        """A read that comes back short is a broken read, not empty stock."""
        self._run(self._fake())
        self.assertEqual(self.matched.reza_edbert_free_qty, 100.0)

        self.env["ir.config_parameter"].sudo().set_str(self.sync.PARAM_MIN_ROWS, 50)
        fake = FakeWholesale(
            quants=[quant(9001, 1.0)], products={9001: "REZA-MATCH"}
        )
        with self.assertRaises(UserError) as caught:
            self._run(fake)
        self.assertIn("floor", str(caught.exception))
        self.assertEqual(self.matched.reza_edbert_free_qty, 100.0)

    def test_an_all_zero_stock_read_is_refused(self):
        """Every row zero is not a real position for a warehouse this size."""
        self._run(self._fake())
        fake = self._fake(quants=[quant(9001, 0.0), quant(9002, 0.0)])
        with self.assertRaises(UserError) as caught:
            self._run(fake)
        self.assertIn("zero or less", str(caught.exception))
        self.assertEqual(self.matched.reza_edbert_free_qty, 100.0)

    def test_a_location_that_is_not_internal_is_refused(self):
        """A customer or transit location would give plausible wrong numbers."""
        fake = self._fake(
            locations=[
                {
                    "id": LOCATION,
                    "complete_name": "Partners/Customers",
                    "usage": "customer",
                    "company_id": (1, "Edbert Holdings Pty Ltd"),
                }
            ]
        )
        with self.assertRaises(UserError) as caught:
            self._run(fake)
        self.assertIn("internal", str(caught.exception))

    def test_a_location_belonging_to_no_company_is_refused(self):
        """A shared location cannot say whose stock it holds."""
        fake = self._fake(
            locations=[
                {
                    "id": LOCATION,
                    "complete_name": "Virtual Locations/Inter-company transit",
                    "usage": "internal",
                    "company_id": False,
                }
            ]
        )
        with self.assertRaises(UserError) as caught:
            self._run(fake)
        self.assertIn("no company", str(caught.exception))

    def test_a_missing_location_is_refused(self):
        fake = self._fake(locations=[])
        with self.assertRaises(UserError) as caught:
            self._run(fake)
        self.assertIn("does not exist", str(caught.exception))

    def test_a_collapsed_product_read_is_refused(self):
        """The stock floor cannot see this one.

        If the product read returns nothing, every matched product silently
        becomes unmatched and the whole catalogue stops showing figures.
        """
        self._run(self._fake())
        fake = self._fake(products={})
        with self.assertRaises(UserError) as caught:
            self._run(fake)
        self.assertIn("returned nothing", str(caught.exception))
        self.assertEqual(self.matched.reza_edbert_stock_state, "ok")
        self.assertEqual(self.matched.reza_edbert_free_qty, 100.0)

    def test_a_halved_product_read_is_refused(self):
        """A partial collapse is refused as well as a total one."""
        self.env["ir.config_parameter"].sudo().set_str(
            self.sync.PARAM_LAST_RESOLVED, 100
        )
        with self.assertRaises(UserError) as caught:
            self._run(self._fake())
        self.assertIn("less than half", str(caught.exception))

    def test_a_run_that_takes_too_long_gives_up_before_writing(self):
        """The socket timeout is per call; this is the deadline for the run."""
        self._run(self._fake())
        self.assertEqual(self.matched.reza_edbert_free_qty, 100.0)
        self.patch(type(self.env[SYNC]), "_run_budget_seconds", lambda self: 0)
        # A different figure, so that "the old value survived" is evidence the
        # run wrote nothing rather than evidence it wrote the same number.
        slower = self._fake(quants=[quant(9001, 7.0), quant(9003, 500.0)])
        with self.assertRaises(UserError) as caught:
            self._run(slower)
        self.assertIn("given up", str(caught.exception))
        self.assertEqual(self.matched.reza_edbert_free_qty, 100.0)

    def test_a_missing_credential_is_refused(self):
        """A password that has expired must say so, not read as empty stock."""
        self.env["res.company"].sudo().search(
            [("external_api", "=", True)]
        ).write({"external_api_password": False})
        with self.assertRaises(UserError) as caught:
            self.env[SYNC].run()
        self.assertIn("credentials", str(caught.exception))

    # ------------------------------------------------------------------
    # Cost of a run
    # ------------------------------------------------------------------
    def test_an_unchanged_figure_is_not_written_again(self):
        """A run must not rewrite the catalogue when nothing has moved."""
        first = self._run(self._fake())
        self.assertEqual(first, len(self.all_ids))
        stamp = self.matched.reza_edbert_stock_date
        second = self._run(self._fake())
        self.assertEqual(second, 0)
        self.assertEqual(self.matched.reza_edbert_stock_date, stamp)

    def test_the_last_checked_time_moves_even_when_nothing_changed(self):
        """Staff need to know the figure is fresh, not only that it moved."""
        self._run(self._fake())
        self.assertTrue(self.env[SYNC]._last_sync())
        self.assertTrue(self.matched.reza_edbert_last_sync)

    # ------------------------------------------------------------------
    # What the template shows
    # ------------------------------------------------------------------
    def test_a_plain_user_cannot_start_a_run(self):
        """Odoo 18 puts NO access check on an RPC method call.

        get_public_method (odoo/service/model.py:29) checks the name and the
        @api.private marker and nothing else, and an AbstractModel has no table
        so no ir.model.access row can gate it. Without this guard any registered
        shopper could start a run against the wholesale production database.
        """
        user = self.env["res.users"].create(
            {
                "name": "Edbert stock test bystander",
                "login": "reza_edbert_stock_bystander",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        with self.assertRaises(AccessError) as caught:
            self.env[SYNC].with_user(user).sudo(False).run()
        self.assertIn("inventory manager", str(caught.exception))

    def test_the_cron_runs_under_a_superuser_environment(self):
        """Whatever else changes, the cron must not lock itself out.

        Its Scheduler User is base.user_root, and Environment.__new__
        (odoo/api.py:570-573) sets su for SUPERUSER_ID. Asserting env.su inside
        a TransactionCase would prove nothing -- the test itself runs as uid 1
        -- so the cron record is read and the environment built from it.
        """
        cron = self.env.ref("reza_ecom_edbert_stock.ir_cron_reza_edbert_stock")
        self.assertEqual(cron.user_id, self.env.ref("base.user_root"))
        self.assertTrue(self.env(user=cron.user_id.id).su)

    def test_the_superuser_leg_works_without_the_group(self):
        """The su leg must stand on its own.

        On a database with `stock` installed, base.user_root is a member of
        stock.group_stock_manager by core data (stock/security/stock_security.xml),
        so the membership branch would admit the cron anyway and hide a broken
        su leg. This drives a superuser environment whose user is NOT a member,
        which is the only way to see that leg work.
        """
        plain = self.env["res.users"].create(
            {
                "name": "Edbert stock test non-manager",
                "login": "reza_edbert_stock_non_manager",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.assertFalse(plain.has_group("stock.group_stock_manager"))
        su_env = self.env(user=plain, su=True)
        self.assertTrue(su_env.su)
        # Must not raise.
        self.env[SYNC].with_env(su_env)._check_allowed()

    def test_the_stock_read_is_bounded_by_company_as_well_as_location(self):
        """`child_of` alone is not a company guard.

        stock.location.company_id is not tied to its parent's, so a child
        created under WH/Stock while another company was active would be
        counted under a field labelled for Edbert.
        """
        fake = self._fake()
        self._run(fake)
        self.assertIn(
            ("company_id", "=", 1),
            [tuple(leaf) for leaf in fake.quant_domain],
        )
        self.assertIn(
            ("location_id", "child_of", LOCATION),
            [tuple(leaf) for leaf in fake.quant_domain],
        )

    def test_the_figures_are_hidden_from_portal_and_public_users(self):
        """website_sale grants portal and public READ on product.product.

        So a field with no groups= is readable over call_kw by anyone who can
        register an account -- and these carry a supplier's stock position and
        its internal reference codes.

        The check is made against the field-access mechanism itself rather than
        by reading a record. A record read would raise for a portal user on an
        unpublished product whatever the field carried, and the test would then
        pass whether or not the restriction existed. `default_code` is read
        first as a control: if that were refused too, this test would be
        proving nothing.
        """
        for group in ("base.group_portal", "base.group_public"):
            reader = self.env["res.users"].create(
                {
                    "name": "Edbert stock test %s" % group,
                    "login": "reza_edbert_stock_%s" % group.replace(".", "_"),
                    "group_ids": [(6, 0, [self.env.ref(group).id])],
                }
            )
            variants = self.env["product.product"].with_user(reader).sudo(False)
            templates = self.env["product.template"].with_user(reader).sudo(False)
            self.assertFalse(variants.env.su, "the check is meaningless under su")

            # Control: an ordinary field IS accessible to this user.
            variants.check_field_access(variants._fields["default_code"], "read")

            for field in (
                "reza_edbert_free_qty",
                "reza_edbert_stock_state",
                "reza_edbert_code",
                "reza_edbert_stock_date",
                "reza_edbert_last_sync",
            ):
                with self.assertRaises(AccessError, msg=field):
                    variants.check_field_access(variants._fields[field], "read")
            for field in (
                "reza_edbert_total_free_qty",
                "reza_edbert_unmatched_count",
                "reza_edbert_last_sync",
            ):
                with self.assertRaises(AccessError, msg=field):
                    templates.check_field_access(templates._fields[field], "read")

    def test_a_location_owned_by_another_company_is_refused(self):
        """Liaise and Global both hold internal locations with a company.

        So "internal, and owned by somebody" does not identify Edbert, and a
        mistyped setting would write Liaise's stock under an Edbert label.
        """
        fake = self._fake(
            locations=[
                {
                    "id": LOCATION,
                    "complete_name": "LWH/Stock",
                    "usage": "internal",
                    "company_id": (2, "LIAISE INTERNATIONAL PTY LTD"),
                }
            ]
        )
        with self.assertRaises(UserError) as caught:
            self._run(fake)
        self.assertIn("LIAISE", str(caught.exception))

    def test_the_run_resolves_only_the_ids_it_will_consult(self):
        """Mixing the quant ids into the read makes the collapse guard soft.

        If the referenced ids all fail to resolve while the quant ids resolve,
        a guard written over both populations passes and every product silently
        becomes unmatched.
        """
        seen = []
        model_class = type(self.env[SYNC])
        original = model_class._read_identifiers

        def spy(self, call, wholesale_ids, started_at):
            seen.append(set(wholesale_ids))
            return original(self, call, wholesale_ids, started_at)

        self.patch(model_class, "_read_identifiers", spy)
        # 9999 is stock on a wholesale product no ecom product maps to. Without
        # a quant id that is absent from the referenced set, the two
        # populations are identical in this fixture and the test cannot see the
        # difference it exists to police.
        fake = self._fake(
            quants=[
                quant(9001, 120.0, 20.0),
                quant(9002, 0.0),
                quant(9003, 500.0),
                quant(9999, 12.0),
            ]
        )
        self._run(fake)
        self.assertEqual(len(seen), 1)
        # Referenced: 9001-9004, the last being the dead id. 9999 is stock
        # nobody asked about, so it must never reach the read.
        self.assertEqual(seen[0], {9001, 9002, 9003, 9004})
        self.assertNotIn(9999, seen[0])

    def test_the_template_sums_its_variants_and_counts_the_unmatched(self):
        attribute = self.env["product.attribute"].create(
            {"name": "Edbert Test Size", "create_variant": "always"}
        )
        values = self.env["product.attribute.value"].create(
            [
                {"name": "Edbert Test A", "attribute_id": attribute.id},
                {"name": "Edbert Test B", "attribute_id": attribute.id},
            ]
        )
        template = self.env["product.template"].create(
            {
                "name": "Edbert stock test run",
                "attribute_line_ids": [
                    (
                        0,
                        0,
                        {"attribute_id": attribute.id, "value_ids": [(6, 0, values.ids)]},
                    )
                ],
            }
        )
        variants = template.product_variant_ids
        self.assertEqual(len(variants), 2)
        variants[0].write({"default_code": "REZA-VAR-A", "external_api_id": 9101})
        variants[1].write({"default_code": "REZA-VAR-B", "external_api_id": 9102})

        fake = self._fake(
            quants=[quant(9101, 40.0, 10.0)],
            products={9101: "REZA-VAR-A"},
        )
        self._run(fake, products=variants)

        self.assertEqual(variants[0].reza_edbert_stock_state, "ok")
        self.assertEqual(variants[1].reza_edbert_stock_state, "no_match")
        self.assertEqual(template.reza_edbert_total_free_qty, 30.0)
        self.assertEqual(template.reza_edbert_unmatched_count, 1)

    def test_no_ecom_stock_or_availability_is_touched(self):
        """The whole point of this design: it is a number, and nothing else.

        The SYNC writes nothing but the figures. Selling on them is done at
        read time by models/website_stock.py, so `allow_out_of_stock_order`
        must still be left exactly as it was.
        """
        qty_before = self.matched.qty_available
        free_before = self.matched.free_qty
        quants_before = self.env["stock.quant"].search_count([])
        has_website_stock = "allow_out_of_stock_order" in self.matched._fields
        if has_website_stock:
            oos_before = self.matched.allow_out_of_stock_order

        self._run(self._fake())

        self.assertEqual(self.matched.qty_available, qty_before)
        self.assertEqual(self.matched.free_qty, free_before)
        self.assertEqual(self.env["stock.quant"].search_count([]), quants_before)
        if has_website_stock:
            self.assertEqual(self.matched.allow_out_of_stock_order, oos_before)
        else:
            _logger.info(
                "website_sale_stock is absent, so the availability check was "
                "not exercised."
            )
