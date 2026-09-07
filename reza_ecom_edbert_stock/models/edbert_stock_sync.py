# -*- coding: utf-8 -*-
"""Pull Edbert's free stock figures into ecom, for staff to look at.

The run is read-only against the wholesale database and writes four display
fields on ecom products. It creates no quant, posts no journal entry and
changes no availability setting.

Everything here fails closed. Where the run cannot prove a figure is right it
withholds the figure and records why, rather than showing a number that might
belong to another product.
"""

import logging
import time
import xmlrpc.client
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

# Read this many wholesale ids per call. Small enough that one slow call does
# not hold the whole run, large enough that the call count stays modest.
CHUNK = 400


class _TimeoutTransport(xmlrpc.client.SafeTransport):
    """xmlrpc.client.ServerProxy has no timeout of its own.

    Without one a hung wholesale server holds this run open indefinitely, and
    on a cron that means the worker never comes back.
    """

    def __init__(self, timeout, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reza_timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self._reza_timeout
        return connection


class _PlainTimeoutTransport(xmlrpc.client.Transport):
    """The http:// counterpart of _TimeoutTransport."""

    def __init__(self, timeout, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reza_timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self._reza_timeout
        return connection


class RezaEdbertStockSync(models.AbstractModel):
    _name = "reza.edbert.stock.sync"
    _description = "Edbert Stock Sync"

    # ------------------------------------------------------------------
    # Settings. Each one is an ir.config_parameter so it can be corrected
    # without a deploy.
    # ------------------------------------------------------------------
    PARAM_LOCATION = "reza_ecom_edbert_stock.location_id"
    PARAM_MIN_ROWS = "reza_ecom_edbert_stock.min_quant_rows"
    PARAM_TIMEOUT = "reza_ecom_edbert_stock.timeout_seconds"
    PARAM_LAST_SYNC = "reza_ecom_edbert_stock.last_sync"
    PARAM_LAST_RESOLVED = "reza_ecom_edbert_stock.last_resolved"
    PARAM_COMPANY = "reza_ecom_edbert_stock.wholesale_company_id"
    PARAM_MAX_SECONDS = "reza_ecom_edbert_stock.max_run_seconds"

    # Edbert's WH/Stock. Measured on production 2026-09-07: it is the only
    # internal location Edbert owns, and it holds every unit ecom can buy.
    DEFAULT_LOCATION = 8
    # Edbert Holdings Pty Ltd on the wholesale database. Liaise (LWH/Stock, 28)
    # and Global (GWH/Stock, 36) are internal locations carrying a company too,
    # so "internal, and owned by somebody" does not identify Edbert. Without
    # this, a mistyped location setting would write Liaise's stock into a field
    # labelled "Edbert Free Qty" and every guard would pass.
    DEFAULT_COMPANY = 1
    # Measured the same day: 2,854 quant rows. A read that comes back far
    # shorter than that is a broken read, not an empty warehouse.
    DEFAULT_MIN_ROWS = 500
    DEFAULT_TIMEOUT = 120
    # The socket timeout above is per call, not per run. The identifier read
    # alone is about 39 calls, so a server answering slowly but not failing
    # could hold a cron worker for over an hour on an hourly schedule. This is
    # the deadline for the whole run.
    DEFAULT_MAX_SECONDS = 600

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------
    def _param(self):
        return self.env["ir.config_parameter"].sudo()

    def _int_param(self, key, default):
        """Read a whole-number setting, falling back to the shipped default.

        An unset parameter reads as False, and int(False) is 0 rather than an
        error -- so a plain int() here would silently resolve every setting to
        zero on a fresh install. The location check would then refuse every
        run, and the figures would never appear.
        """
        raw = self._param().get_param(key)
        if raw is None or raw is False or not str(raw).strip():
            return default
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            _logger.warning(
                "Setting %s reads %r, which is not a whole number. Using %s.",
                key,
                raw,
                default,
            )
            return default

    def _last_sync(self):
        raw = self._param().get_param(self.PARAM_LAST_SYNC)
        if not raw:
            return False
        try:
            return fields.Datetime.to_datetime(raw)
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def _credential_company(self):
        """Return the company holding the wholesale credentials.

        All three configured companies point at the same wholesale database
        (verified on production 2026-09-07), so the lowest id is as good as any.
        The credentials are read rather than duplicated, so this module adds no
        new place for them to live.
        """
        company = (
            self.env["res.company"]
            .sudo()
            .search([("external_api", "=", True)], order="id asc")
            .filtered(
                lambda c: c.external_api_url
                and c.external_api_db
                and c.external_api_username
                and c.external_api_password
            )[:1]
        )
        if not company:
            raise UserError(
                _(
                    "No company carries a complete set of wholesale API "
                    "credentials. Set them under Settings, External API, "
                    "before this can run."
                )
            )
        return company

    def _connect(self, company):
        timeout = self._int_param(self.PARAM_TIMEOUT, self.DEFAULT_TIMEOUT)
        url = (company.external_api_url or "").rstrip("/")
        transport = (
            _PlainTimeoutTransport(timeout)
            if url.startswith("http://")
            else _TimeoutTransport(timeout)
        )
        common = xmlrpc.client.ServerProxy(
            "%s/xmlrpc/2/common" % url, transport=transport, allow_none=True
        )
        uid = common.authenticate(
            company.external_api_db,
            company.external_api_username,
            company.external_api_password,
            {},
        )
        if not uid:
            raise UserError(
                _(
                    "The wholesale database refused the credentials on company "
                    "%s. The password has most likely expired.",
                    company.display_name,
                )
            )
        proxy = xmlrpc.client.ServerProxy(
            "%s/xmlrpc/2/object"
            % url,
            transport=(
                _PlainTimeoutTransport(timeout)
                if url.startswith("http://")
                else _TimeoutTransport(timeout)
            ),
            allow_none=True,
        )

        def call(model, method, args, kwargs=None):
            return proxy.execute_kw(
                company.external_api_db,
                uid,
                company.external_api_password,
                model,
                method,
                args,
                kwargs or {},
            )

        return call

    # ------------------------------------------------------------------
    # Remote reads
    # ------------------------------------------------------------------
    def _check_location(self, call, location_id):
        """Refuse any location that is not the expected company's own stock.

        The location id is a setting, so a typo could point this run at a
        customer location, a transit location or another company's warehouse.
        Every one of those produces a plausible-looking set of numbers under a
        field label that then lies about whose stock it is.
        """
        rows = call(
            "stock.location",
            "search_read",
            [[("id", "=", location_id)]],
            {"fields": ["complete_name", "usage", "company_id"]},
        )
        if not rows:
            raise UserError(
                _(
                    "Wholesale location %s does not exist. Check the setting %s.",
                    location_id,
                    self.PARAM_LOCATION,
                )
            )
        location = rows[0]
        if location["usage"] != "internal":
            raise UserError(
                _(
                    "Wholesale location %(name)s is a %(usage)s location, not an "
                    "internal one. It holds no sellable stock, so this run stops.",
                    name=location["complete_name"],
                    usage=location["usage"],
                )
            )
        if not location["company_id"]:
            raise UserError(
                _(
                    "Wholesale location %s belongs to no company, so this run "
                    "cannot tell whose stock it holds.",
                    location["complete_name"],
                )
            )
        expected = self._int_param(self.PARAM_COMPANY, self.DEFAULT_COMPANY)
        if location["company_id"][0] != expected:
            raise UserError(
                _(
                    "Wholesale location %(name)s belongs to %(owner)s, not to "
                    "the company this figure is labelled for. Nothing has been "
                    "changed. Correct the setting %(setting)s, or point "
                    "%(location_setting)s at the right warehouse.",
                    name=location["complete_name"],
                    owner=location["company_id"][1],
                    setting=self.PARAM_COMPANY,
                    location_setting=self.PARAM_LOCATION,
                )
            )
        return location

    def _read_quants(self, call, location_id, company_id):
        """Read the stock, bounded by BOTH the location tree and the company.

        `child_of` is what keeps a sub-location added at Edbert from silently
        dropping out of the figure. But `stock.location.company_id` is not tied
        to its parent's -- core only blocks a change after creation
        (stock/models/stock_location.py:67-70) -- so a child created while
        another company was active would otherwise be counted under a field
        labelled for Edbert. The company leaf closes that.
        """
        rows = call(
            "stock.quant",
            "search_read",
            [[
                ("location_id", "child_of", location_id),
                ("company_id", "=", company_id),
            ]],
            {"fields": ["product_id", "quantity", "reserved_quantity"]},
        )
        minimum = self._int_param(self.PARAM_MIN_ROWS, self.DEFAULT_MIN_ROWS)
        if len(rows) < minimum:
            raise UserError(
                _(
                    "The wholesale stock read returned %(got)s rows against a "
                    "floor of %(floor)s. A read this short is a broken read, not "
                    "an empty warehouse, so nothing has been changed.",
                    got=len(rows),
                    floor=minimum,
                )
            )

        free = defaultdict(float)
        for row in rows:
            product_id = row["product_id"][0] if row["product_id"] else False
            if not product_id:
                continue
            free[product_id] += (row["quantity"] or 0.0) - (
                row["reserved_quantity"] or 0.0
            )
        if not any(value > 0 for value in free.values()):
            raise UserError(
                _(
                    "Every row of the wholesale stock read is zero or less. That "
                    "is not a real position, so nothing has been changed."
                )
            )
        return free

    def _run_budget_seconds(self):
        return self._int_param(self.PARAM_MAX_SECONDS, self.DEFAULT_MAX_SECONDS)

    def _check_budget(self, started_at, what):
        """Stop a run that is taking too long, before it writes anything.

        Every caller sits ahead of the first write, so a run that gives up here
        has changed nothing. It is checked around the stock read as well as
        between the identifier chunks, because a single slow call is enough to
        hold a cron worker and the chunk loop runs zero times when nothing is
        mapped.
        """
        elapsed = time.monotonic() - started_at
        if elapsed >= self._run_budget_seconds():
            raise UserError(
                _(
                    "Reading %(what)s from the wholesale database has taken "
                    "%(elapsed)s seconds. The run has given up rather than hold "
                    "the job open, and nothing has been changed.",
                    what=what,
                    elapsed=int(elapsed),
                )
            )

    def _read_identifiers(self, call, wholesale_ids, started_at):
        """Return {wholesale id: (internal reference, set of identifiers)}.

        Missing ids are simply absent. A `read` would raise on an id that no
        longer exists, and 5,374 of the stored ids no longer do. `search_read`
        on the id leaves them out instead, which is the answer this run wants.

        Two identifier fields are read, because the two catalogues label the
        same product differently. Measured on production 2026-09-07: of the 31
        products whose internal references disagree, every single one carries
        the ecom reference in its barcode. Ecom knows Rocko's Tread Thongs size
        08 as `9340457002310`; wholesale knows it as `4178Treads08` with that
        number in the barcode. Checking the reference alone would have withheld
        all 31 figures, 15 of them on published products.

        `reza_generic_barcode` is deliberately NOT read. It is a model-level
        number shared by every size of a product, so it cannot tell size 08
        from size 14 and would happily verify the wrong variant. `barcode`
        carries a uniqueness constraint, so it can.
        """
        found = {}
        ids = sorted(set(wholesale_ids))
        for start in range(0, len(ids), CHUNK):
            self._check_budget(
                started_at, _("product references (%s so far)", len(found))
            )
            chunk = ids[start : start + CHUNK]
            rows = call(
                "product.product",
                "search_read",
                [[("id", "in", chunk)]],
                {
                    "fields": ["default_code", "barcode"],
                    "context": {"active_test": False},
                },
            )
            for row in rows:
                identifiers = {
                    str(value).strip()
                    for value in (row.get("default_code"), row.get("barcode"))
                    if value and str(value).strip()
                }
                found[row["id"]] = (row.get("default_code") or "", identifiers)
        return found

    # ------------------------------------------------------------------
    # The run
    # ------------------------------------------------------------------
    @api.private
    def run(self):
        """Refresh every product's Edbert figure.

        Guarded twice on purpose. Odoo 18's only gate on an RPC method call is
        `get_public_method` (odoo/service/model.py:29), which checks the name
        and the @api.private marker and performs NO access check at all. An
        AbstractModel has no table, so no ir.model.access row can gate it
        either. Without both guards any authenticated session -- including a
        registered shopper, who is a real res.users -- could start a run
        against the wholesale production database.

        The env.su leg lets the cron through: it runs as base.user_root, and
        Environment.__new__ (odoo/api.py:570-573) sets su for SUPERUSER_ID.
        It is not decorative -- sudo() does not satisfy has_group().
        """
        self._check_allowed()
        started_at = time.monotonic()
        Product = self.env["product.product"].sudo()

        company = self._credential_company()
        call = self._connect(company)

        location_id = self._int_param(self.PARAM_LOCATION, self.DEFAULT_LOCATION)
        location = self._check_location(call, location_id)
        self._check_budget(started_at, _("the warehouse settings"))
        free_by_id = self._read_quants(call, location_id, location["company_id"][0])
        self._check_budget(started_at, _("the stock position"))

        local = Product.search_read(
            self._product_domain(),
            [
                "default_code",
                "external_api_id",
                "reza_edbert_free_qty",
                "reza_edbert_stock_state",
                "reza_edbert_code",
            ],
        )

        referenced = {row["external_api_id"] for row in local if row["external_api_id"]}
        # Only the referenced ids, never the quant ids. _plan consults nothing
        # else, and mixing the two populations lets the collapse guard below
        # pass on quant ids while every referenced id failed to resolve.
        identifiers = self._read_identifiers(call, referenced, started_at)
        self._check_resolution(identifiers, referenced)

        planned = self._plan(local, free_by_id, identifiers)
        changed = self._apply(Product, planned)

        self._param().set_param(self.PARAM_LAST_SYNC, fields.Datetime.now())
        self._param().set_param(self.PARAM_LAST_RESOLVED, len(identifiers))

        _logger.info(
            "Edbert stock sync: location %s, %s products with stock, "
            "%s ecom products read, %s rows changed, %ss.",
            location["complete_name"],
            len(free_by_id),
            len(local),
            changed,
            int(time.monotonic() - started_at),
        )
        return changed

    def _product_domain(self):
        """Which ecom products carry a figure.

        Archived products are left alone: nobody sees them, and rewriting them
        would double the size of every run for no benefit.
        """
        return [("active", "=", True)]

    def _check_resolution(self, identifiers, referenced):
        """Refuse a run whose product read collapsed.

        The quant floor cannot see this. If the product read came back empty
        while ids were asked for, every matched product would silently become
        unmatched and the whole catalogue would stop showing figures.
        """
        if referenced and not identifiers:
            raise UserError(
                _(
                    "The wholesale product read returned nothing while %s ids "
                    "were asked for. Nothing has been changed.",
                    len(referenced),
                )
            )
        previous = self._int_param(self.PARAM_LAST_RESOLVED, 0)
        if previous and len(identifiers) * 2 < previous:
            raise UserError(
                _(
                    "The wholesale product read resolved %(now)s ids against "
                    "%(before)s on the last run. That is less than half, so this "
                    "run stops rather than clearing figures across the "
                    "catalogue.",
                    now=len(identifiers),
                    before=previous,
                )
            )

    def _plan(self, local, free_by_id, identifiers):
        """Decide the four field values for every ecom product.

        Grouped by the values themselves. The two large populations -- the
        unmatched, and the matched holding no stock -- collapse into one write
        each. Products that DO hold stock mostly carry distinct quantities, so
        each is its own write: expect roughly one call per product with stock
        on a first full run, and far fewer afterwards, because a row whose
        figure has not moved is skipped entirely.
        """
        planned = defaultdict(list)
        for row in local:
            wholesale_id = row["external_api_id"]
            entry = identifiers.get(wholesale_id) if wholesale_id else None

            if entry is None:
                # No mapping at all, or a mapping to an id that has since been
                # deleted from the wholesale catalogue.
                state, quantity, code = "no_match", 0.0, False
            elif not row["default_code"]:
                # Nothing on this side to check the mapping against. The figure
                # may well be right; it cannot be shown to be right.
                state, quantity, code = "unverified", 0.0, entry[0] or False
            elif str(row["default_code"]).strip() not in entry[1]:
                # The mapping points somewhere, and that somewhere carries
                # neither this reference nor this barcode. Withhold the figure
                # and record what was found instead.
                state, quantity, code = "mismatch", 0.0, entry[0] or False
            else:
                # Verified. A product Edbert holds no stock of is a truthful
                # zero, not a failed match.
                state = "ok"
                quantity = max(0.0, free_by_id.get(wholesale_id, 0.0))
                code = False

            unchanged = (
                state == row["reza_edbert_stock_state"]
                and code == (row["reza_edbert_code"] or False)
                and abs(quantity - (row["reza_edbert_free_qty"] or 0.0)) < 0.0001
            )
            if not unchanged:
                planned[(quantity, state, code)].append(row["id"])
        return planned

    def _apply(self, Product, planned):
        now = fields.Datetime.now()
        changed = 0
        for (quantity, state, code), ids in planned.items():
            Product.browse(ids).write(
                {
                    "reza_edbert_free_qty": quantity,
                    "reza_edbert_stock_state": state,
                    "reza_edbert_code": code,
                    "reza_edbert_stock_date": now,
                }
            )
            changed += len(ids)
        return changed

    def _check_allowed(self):
        if self.env.su:
            return
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError(
                _(
                    "Refreshing the Edbert stock figures reads the wholesale "
                    "production database. Only an inventory manager may start "
                    "it by hand."
                )
            )

    @api.model
    @api.private
    def cron_sync_edbert_stock(self):
        return self.run()
