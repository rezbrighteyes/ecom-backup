# Review pass 1 — granular

Read line by line against Odoo 18 APIs. Nine defects, four of them would have broken
something on install or in production. All fixed in the committed code; recorded here
because "reviewed" means nothing without the list.

| # | Severity | File | Defect | Fix |
|---|---|---|---|---|
| 1 | **Breaks the page** | `views/stockist_templates.xml` | The ItemList JSON-LD called `json.dumps(...)` inside a `t-esc` expression. QWeb has no `json` in scope, so `/stockists` would raise `NameError` on every request. | JSON-LD is now built in the controller and passed in as a string. Templates render values, they do not compute them. |
| 2 | **SEO defect** | `controllers/main.py` | Unpublished / wrong-website stockists returned `request.render("website.page_404")` — which serves the 404 *page* with **HTTP 200**. A soft 404 invites Google to index a "not found" page. | Returns `request.not_found()`, a real 404 status. |
| 3 | **Install failure risk** | `__manifest__.py` | Model inherits `mail.thread` and the form uses `<chatter/>`, but `mail` was not in `depends` — it was only reaching us transitively through `website → portal → mail`. Transitive dependencies are not a contract. | `mail` added explicitly. |
| 4 | **Data leak** | `security/ir.model.access.csv` | Public and portal groups had model-wide read. Combined with the `/web/image/...` route that needs it, that exposes **unpublished** stockists' fields. | Kept the ACL (the image route requires it) and added an `ir.rule` restricting public/portal to `is_published = True`. Defence at the row level, where it belongs. |
| 5 | Logic bug | `models/stockist.py` | `rec.state_id.code or rec.state_id.name if rec.state_id else None` parses as `code or (name if state_id else None)`, not what it reads as. It happened to work only because `.code` on an empty recordset returns `False`. | Rewritten as an explicit block. |
| 6 | Fragile | `models/stockist.py` | `self.env["ir.http"]._slug(rec)` is the Odoo 17.4+ API. On an older minor it raises `AttributeError` and every stockist URL breaks. | Wrapped in a helper that falls back to the legacy `http_routing` `slug()` import. |
| 7 | Name collision | `models/stockist.py` | `_website_domain` is also defined by `website.multi.mixin`. If this model ever gains that mixin the override changes meaning silently. | Renamed to `_stockist_website_domain`. |
| 8 | Data integrity | `models/stockist.py` | `unique(store_code)` does not catch duplicates when the code is an **empty string** — Postgres allows many `''` but only ignores `NULL`. | Empty codes are normalised to `NULL` on write. |
| 9 | Cosmetic | `views/stockist_views.xml` | `oe_button_box` was placed after `oe_title`; Odoo expects it before, and it renders in the wrong spot. | Moved above the title block. |

## What I checked and found correct

- `sitemap=` callback signature `(env, rule, qs)` matches what Odoo passes.
- `<list>` (not `<tree>`) — correct for Odoo 18.
- `<chatter/>` — correct Odoo 18 syntax; the 17-style `<div class="oe_chatter">` is gone.
- Recordset slicing for the pager, and `website.pager` context key, both correct.
- `brand_last` — QWeb does supply `<name>_last` for `t-foreach`.
- `/web/image/website.stockist/<id>/image_1920` — correct dotted-model URL form.
- `many2many_tags` on `website_ids` with `no_create` — cannot accidentally create a website.
