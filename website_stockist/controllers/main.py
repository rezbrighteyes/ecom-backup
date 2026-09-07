# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

PER_PAGE = 60


def _sitemap_stockists(env, rule, qs):
    """Emit every published stockist visible on the current website.

    Odoo calls this while building /sitemap.xml. It must yield dicts with a
    'loc' key. Anything not yielded here never reaches the sitemap.
    """
    Stockist = env["website.stockist"]
    website = env["website"].get_current_website()
    domain = Stockist._get_published_domain(website.id)
    stockists = Stockist.sudo().search(domain)

    # lastmod is what Google reads to decide whether a page is worth
    # recrawling. Odoo emits it for website.page records and nothing else, so
    # 553 of 556 URLs on this site carry no date at all. These can: a stockist
    # is a real record with a real write_date.
    index_loc = "/stockists"
    if not qs or qs.lower() in index_loc:
        entry = {"loc": index_loc}
        newest = max(stockists.mapped("write_date"), default=None)
        if newest:
            entry["lastmod"] = newest.date()
        yield entry
    for stockist in stockists:
        loc = stockist.website_url
        if qs and qs.lower() not in loc.lower():
            continue
        entry = {"loc": loc}
        if stockist.write_date:
            entry["lastmod"] = stockist.write_date.date()
        yield entry


class WebsiteStockistController(http.Controller):

    def _published_stockists(self, extra_domain=None):
        """Stockists visible to the public on the current website."""
        Stockist = request.env["website.stockist"]
        website = request.env["website"].get_current_website()
        domain = Stockist._get_published_domain(website.id)
        if extra_domain:
            domain = domain + extra_domain
        return Stockist.sudo().search(domain)

    @http.route(
        ["/stockists", "/stockists/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
        sitemap=_sitemap_stockists,
    )
    def stockist_index(self, page=1, state=None, **kwargs):
        extra_domain = []
        if state:
            extra_domain += ["|", ("state_id.code", "=ilike", state),
                             ("state_id.name", "=ilike", state)]
        # The filter bar has to list every state that has stockists, not only
        # the state currently selected. Building it from the filtered set
        # leaves one button on screen and no way back to the other states.
        all_stockists = self._published_stockists()
        stockists = self._published_stockists(extra_domain) if state else all_stockists

        total = len(stockists)
        pager = request.website.pager(
            url="/stockists",
            total=total,
            page=page,
            step=PER_PAGE,
            scope=5,
            url_args={"state": state} if state else None,
        )
        offset = pager["offset"]
        page_records = stockists[offset:offset + PER_PAGE]

        # Group for display: state -> stockists, in the model's own order.
        grouped = {}
        for rec in page_records:
            key = rec.state_id
            grouped.setdefault(key, request.env["website.stockist"])
            grouped[key] |= rec
        grouped = sorted(
            grouped.items(),
            key=lambda kv: (kv[0].name or "") if kv[0] else "",
        )

        states = all_stockists.mapped("state_id").sorted(lambda s: s.name or "")

        # A state-filtered view is a subset of /stockists, not a page of its
        # own. Without a canonical back to the unfiltered index each state
        # becomes a thin near-duplicate competing with it.
        base_url = request.httprequest.url_root
        filter_canonical = "%s/stockists" % base_url.rstrip("/") if state else False

        return request.render(
            "website_stockist.stockist_index",
            {
                "stockists": page_records,
                "grouped": grouped,
                "states": states,
                "active_state": state,
                "stockist_canonical": filter_canonical,
                "pager": pager,
                "total": total,
                "base_url": request.httprequest.url_root,
                "json_ld": request.env["website.stockist"]._item_list_json_ld(
                    page_records, request.httprequest.url_root
                ),
            },
        )

    @http.route(
        ['/stockists/<model("website.stockist"):stockist>'],
        type="http",
        auth="public",
        website=True,
        sitemap=False,  # covered by the index rule's sitemap generator
    )
    def stockist_detail(self, stockist, **kwargs):
        # The route converter resolves the record but does NOT apply our
        # publish/website rules, so re-check them here. Without this an
        # unpublished stockist, or one belonging to another website, would be
        # reachable by guessing its URL.
        website = request.env["website"].get_current_website()
        Stockist = request.env["website.stockist"]
        domain = [("id", "=", stockist.id)] + Stockist._get_published_domain(website.id)
        if not Stockist.sudo().search_count(domain):
            if not request.env.user.has_group("website.group_website_designer"):
                # A real 404 status. request.render() would serve the 404 *page*
                # with HTTP 200, which is a soft 404 and gets indexed.
                return request.not_found()
        stockist = stockist.sudo()
        return request.render(
            "website_stockist.stockist_detail",
            {
                "stockist": stockist,
                "main_object": stockist,
                "base_url": request.httprequest.url_root,
                "json_ld": stockist._json_ld(request.httprequest.url_root),
                "stockist_canonical": stockist._canonical_url(website) or False,
                "opening_hours": stockist._opening_hours_list(),
            },
        )
