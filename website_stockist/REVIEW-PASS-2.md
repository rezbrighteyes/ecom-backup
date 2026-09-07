# Review pass 2 — big picture

Pass 1 read the code. This pass asks whether the design is right, and it found one
issue that matters more than anything in pass 1.

---

## 1. The multi-website design reproduces the duplication problem we just fixed — FIXED

A stockist assigned to three websites gets **the same URL path on all three domains**:

```
https://www.mangrovejacks.net.au/stockists/brighteyes-cairns-central-12
https://www.ecomsuperstore.com.au/stockists/brighteyes-cairns-central-12
https://www.whatyouneed.com.au/stockists/brighteyes-cairns-central-12
```

Identical content, three group-owned domains, each self-canonicalising. That is
character-for-character the defect found on 26 Aug with `plush-ball-jellies-pets-17084`
— and this module would have manufactured it deliberately, at 27 records × N sites.

Building a multi-website feature without answering "which domain owns the page" just
industrialises the problem.

**Fix applied:** a `canonical_website_id` field. When a stockist appears on more than
one website, one is nominated as the owner and the other domains emit a cross-domain
`<link rel="canonical">` pointing at it. When it is empty or the stockist is on a single
site, behaviour is unchanged.

**Resolved after checking the live database.** I had flagged this as unverified and left
the override opt-in. A later review read `website.layout` (view 1635) directly and found it
emits its canonical **unconditionally** — so "enable this only if you see two" was wrong
advice, and the duplicate would have shipped. `views/canonical_override.xml` is now loaded
by default with `t-if="not stockist_canonical"`, and the module's canonical is placed in
`<head>` via `<t t-set="head">` rather than in `<body>`, where Google ignores it.

Two further defects came out of that pass and are fixed: `product` was missing from
`depends` (the `brand_ids` m2m needs it and `website` does not pull it in), and the JSON-LD
blocks used `t-esc`, which HTML-escapes quotes inside `<script type="application/ld+json">`
— nothing decodes entities in script content, so **every** JSON-LD block would have been
invalid. They now use `t-out` with a `Markup` value, with `<`, `>` and `&` unicode-escaped
to close a script-tag injection through a stockist name.

---

## 2. "Empty means all websites" is the convention that just caused an incident

Luke asked for the `product.template` convention, and consistency between two models
that sit beside each other is worth more than my preference, so the module follows it.
But it is worth saying plainly: **a new stockist saved with no website ticked publishes
to every site on the instance**, which is exactly how four products ended up on
mangrovejacks.net.au.

Mitigations built in, rather than changing the default behind Luke's back:

- The search view has an **"On every website"** filter, so the audit is one click.
- The form shows the placeholder *"Leave empty to show on ALL websites"* next to the field.
- The list view shows `website_ids` as a visible column by default.

If it bites, the change is a one-line `default=lambda self: self.env['website'].get_current_website()`.

---

## 3. Pagination is unguarded at scale

`/stockists/page/2` and beyond are crawlable through the pager and carry no canonical or
`noindex`. With 27 stockists and 60 per page there is exactly one page today, so nothing
is wrong now. Past ~60 stockists this becomes thin, near-duplicate index pages competing
with each other. Noted rather than pre-solved — guessing at a pagination strategy for a
scale that does not exist is how modules get bloated.

## 4. State filter has a latent mismatch — FIXED

The filter links were built as `?state={code or name}` but matched on `state_id.code`
only. Any state with a blank code produced a link that returned zero results. Now matches
on code **or** name.

## 5. Grouping happens after pagination

Stockists are grouped by state for display, but grouping is applied to the current page,
so one state can be split across two pages with two headings. Cosmetic, and only visible
past 60 records. Left alone.

## 6. Reusing `product.tag` for brands

`brand_ids` points at `product.tag`, which on this database already holds brand-shaped
tags (`MJ`, `WYN`, `Smartcell`, `3SIXT`, `Rocko's`, `Bradfield's`). Reuse beats inventing a
parallel brand table. The risk is that `product.tag` is a general-purpose tag model and
someone may later add non-brand tags to it; the field uses `no_create` so at least nobody
creates tags from the stockist form.

## 7. Added a smoke test

`tests/test_stockist.py` covers the parts most likely to break silently: the
website-scoping domain, empty-`website_ids` fallthrough, `full_address` composition,
store-code normalisation, and that `_json_ld` emits valid parseable JSON with no empty
address node. Run with:

```
odoo -d <db> -i website_stockist --test-enable --stop-after-init
```

---

## What this module deliberately does not do

- **No map widget.** A JS map is what makes existing brand locators uncrawlable — the
  finding behind `TODO/P0-ship-today/42-stockist-reclamation.md`. Every stockist here is a
  server-rendered `<a href>` first. A map can be layered on top later; it must never be
  the only way to reach a stockist.
- **No auto-import of the 27 BrightEyes stores.** `MJ/data/stores.json` holds them, but
  eight have conflicting addresses between the website and Google Business Profile and
  `address_of_record` is unresolved. Importing now would publish a third address variant
  on a domain we own. The importer waits on that decision.

---

## 8. The front-end menu never worked — FIXED

`data/website_menu.xml` created a `website.menu` parented to `website.main_menu` with no
`website_id`, and its comment claimed Odoo would copy it to each website. **Verified false
on the live database:** menu id 1 "Default Main Menu" (`website_id = False`) is a *template*
tree, copied only when a **new** website is created. Every one of the 7 live sites roots at
its own record — Mangrove Jacks at id 27, ecomsuperstore at 10, WhatYouNeed at 40. The
static record would have appeared on **zero** existing websites.

Those roots are runtime records and cannot be referenced from static XML, so the data file
is deleted and replaced with `hooks.py`: `post_init_hook` walks the websites and adds the
entry under each real root, skipping any that already have a `/stockists` menu;
`uninstall_hook` removes them, since code-created records are not cleaned up by uninstall.

## 9. `<t t-set="head">` clobbered anything already in head — FIXED

Both templates set `head` without preserving its prior value. Nothing else sets it on these
routes today, so it was harmless, but any future module or theme adding to `<head>` would
have been silently dropped on stockist pages. Now `<t t-out="head or ''"/>` first.

---

## Still true, and worth repeating

**This module has never been installed and the tests have never been run.** Everything above
is static review plus live reads of the database. The parsers in `models/google_places.py`
were exercised offline against a realistic payload; nothing else has executed. Treat the
first install as the real test — on a staging branch, not `main`.
