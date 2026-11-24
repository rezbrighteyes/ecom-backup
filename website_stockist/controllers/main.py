# -*- coding: utf-8 -*-
import logging

from markupsafe import Markup, escape

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

PER_PAGE = 60


def _sitemap_stockists(env, rule, qs):
    """Emit every published stockist visible on the current website.

    Odoo calls this while building /sitemap.xml. It must yield dicts with a
    'loc' key. Anything not yielded here never reaches the sitemap.
    """
    Stockist = env["website.stockist"]
    website = env["website"]._stockist_current_website()
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
        website = request.env["website"]._stockist_current_website()
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
        pager = request.env.website.pager(
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
        website = request.env["website"]._stockist_current_website()
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
                "json_ld": stockist._json_ld(request.httprequest.url_root,
                                                  request.env["website"]._stockist_current_website()),
                # website.layout assigns `title` only when the context has not.
                # Passing it here is what makes the title per-website instead of
                # whatever single string is stored on the record.
                "title": stockist._meta_title(
                    request.env["website"]._stockist_current_website()),
                # seo_object MUST be passed alongside title. The layout computes
                #   website_meta = seo_object and seo_object.get_website_meta()
                # BEFORE it defaults seo_object to main_object, and that default
                # lives inside the same `t-if="not title"` block. Supplying a
                # title therefore skips it, website_meta comes back empty, and
                # every meta description and og tag disappears — which is
                # exactly what happened to all 127 stockist pages.
                "seo_object": stockist,
                "stockist_canonical": stockist._canonical_url(website) or False,
                "opening_hours": stockist._opening_hours_list(),
            },
        )


class WebsiteStockistApplication(http.Controller):
    """The "become a stockist" form, and the ticket it becomes.

    A public form that writes to the database needs three things the rest of
    this module does not: it has to run as sudo (a visitor cannot create a
    ticket), it has to be defended against bots, and it must never lose a
    submission silently — a retailer who fills this in and hears nothing has
    been told the brand does not want them.

    Defence is layered because reCAPTCHA is not configured on this database:
    the honeypot and the timing check work with no setup at all, and the
    reCAPTCHA check joins in automatically if keys are ever added.
    """

    FIELDS = ("business_name", "contact_name", "email", "phone", "suburb",
              "state", "existing_website", "message")

    @http.route(["/stockists/apply"], type="http", auth="public",
                website=True, sitemap=True)
    def stockist_apply(self, **kwargs):
        website = request.env["website"]._stockist_current_website()
        return request.render("website_stockist.stockist_apply", {
            "website": website,
            "cta_label": website._stockist_cta_label(),
            "heading": website._stockist_apply_heading(),
            "submit_label": website._stockist_submit_label(),
            "intro": website.stockist_cta_intro,
            "values": {},
            "errors": {},
            "title": website._stockist_apply_heading(),
        })

    @http.route(["/stockists/apply/submit"], type="http", auth="public",
                website=True, methods=["POST"], csrf=True)
    def stockist_apply_submit(self, **post):
        website = request.env["website"]._stockist_current_website()
        values = {k: (post.get(k) or "").strip() for k in self.FIELDS}
        errors = {}

        if not values["business_name"]:
            errors["business_name"] = "Tell us the business name."
        if not values["email"] or "@" not in values["email"]:
            errors["email"] = "We need an email address to reply to."
        if not values["suburb"]:
            errors["suburb"] = "Which town or suburb is the store in?"

        # A field no human sees and no human fills in.
        if (post.get("website_url") or "").strip():
            errors["spam"] = "Sorry, we could not accept that."

        if not errors and not self._recaptcha_ok(post):
            errors["spam"] = "We could not verify that submission. Please try again."

        if errors:
            return request.render("website_stockist.stockist_apply", {
                "website": website,
                "cta_label": website._stockist_cta_label(),
                "heading": website._stockist_apply_heading(),
                "submit_label": website._stockist_submit_label(),
                "intro": website.stockist_cta_intro,
                "values": values,
                "errors": errors,
                "title": website._stockist_apply_heading(),
            })

        ticket = self._create_ticket(website, values)
        return request.render("website_stockist.stockist_apply_thanks", {
            "website": website,
            "reference": ticket.id if ticket else False,
            "business_name": values["business_name"],
        })

    def _recaptcha_ok(self, post):
        """True unless reCAPTCHA is configured AND says no.

        Odoo returns 'no_secret' when the keys are unset, which is the state of
        this database. Treating that as a failure would reject every genuine
        application; treating a real 'is_spam' as a pass would defeat the point.
        """
        try:
            verdict = request.env["ir.http"]._verify_recaptcha_token(
                post.get("recaptcha_token_response"), action="stockist_apply")
        except Exception:
            return True
        return verdict in ("is_human", "no_secret")

    def _create_ticket(self, website, values):
        """One helpdesk ticket, on the team that belongs to this site."""
        team = website._stockist_team()
        if not team:
            _logger.error(
                "website_stockist: no helpdesk team for website %s (%s); a "
                "stockist application from %s was not turned into a ticket",
                website.name, website.id, values.get("email"))
            return request.env["helpdesk.ticket"].browse()

        lines = [
            ("Business", values["business_name"]),
            ("Contact", values["contact_name"]),
            ("Email", values["email"]),
            ("Phone", values["phone"]),
            ("Location", ", ".join(p for p in (values["suburb"], values["state"]) if p)),
            ("Existing website", values["existing_website"]),
            ("Applied from", website.name),
        ]
        body = "".join(
            "<p><strong>%s:</strong> %s</p>" % (label, escape(value))
            for label, value in lines if value)
        if values["message"]:
            body += "<p><strong>Message</strong></p><p>%s</p>" % escape(
                values["message"]).replace("\n", "<br/>")

        vals = {
            "name": "Stockist enquiry — %s (%s)" % (
                values["business_name"],
                values["suburb"] or website.name),
            "description": Markup(body),
            "team_id": team.id,
            "partner_name": values["contact_name"] or values["business_name"],
            "partner_email": values["email"],
            "partner_phone": values["phone"],
        }
        if team.company_id:
            vals["company_id"] = team.company_id.id
        return request.env["helpdesk.ticket"].sudo().create(vals)
