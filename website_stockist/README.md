# website_stockist

A stockist / dealer directory for the `ecom-superstore` Odoo 18 instance. Add and remove
stockists from the backend, assign each to any combination of websites, and get a
crawlable, schema-marked public page per stockist.

Built 26 Aug 2026. Reviewed twice — see `REVIEW-PASS-1.md` (granular) and
`REVIEW-PASS-2.md` (design). Nine defects were found and fixed in pass 1; pass 2 found the
cross-domain duplication issue described below.

## Install

Custom modules are installable here — five `d3_*` modules from Dimension3 are already
installed, so this is Odoo.sh or self-hosted, not Odoo Online.

1. Copy `website_stockist/` into the addons path (Odoo.sh: commit it to the repo).
2. Apps → Update Apps List → install **Website Stockists**.
3. Backend menu: **Website → Configuration → Stockists**.
4. Front end: `/stockists`. A post-init hook adds a **Stockists** entry to the menu of
   every existing website; delete it from any site that should not link to it — the pages
   keep working. Uninstalling removes the entries it created.

   A static `website.menu` record cannot do this. On this database `website_id = False`
   marks a **template** tree (menu id 1), which Odoo copies only when a *new* website is
   created — each of the 7 live sites roots at its own record instead (Mangrove Jacks at
   id 27). A static record would have appeared on none of them.

Run the tests:

```
odoo -d dimension3tech-ecom-superstore-main-18331090 -i website_stockist \
     --test-enable --stop-after-init
```

## Multi-website assignment

`website_ids` is a **many2many**, matching `product.template` on this database:

| `website_ids` | Result |
|---|---|
| empty | published on **every** website |
| `[Mangrove Jacks]` | that site only |
| `[Mangrove Jacks, ecomsuperstore]` | both, and neither of the others |

The search view has an **"On every website"** filter so unassigned records can be audited
in one click — the same gap that let four products leak across all three live domains on
26 Aug.

### Cross-domain duplication — read this before assigning a stockist to several sites

A stockist on three websites serves the same URL path on three domains. That is duplicate
content across sibling domains, and it is the exact defect found on the product catalogue.

Set **Canonical website** on any stockist that appears on more than one site. The other
domains then emit a `<link rel="canonical">` pointing at the owner.

This is handled, not left to chance. `website.layout` (view 1635 on this database) emits
its own canonical in `<head>` **unconditionally**, so `views/canonical_override.xml` is
loaded by default and suppresses it with `t-if="not stockist_canonical"`. The module's own
canonical goes into `<head>` via `<t t-set="head">`, preserving anything already there.
Exactly one canonical survives on every page.

## What each stockist page emits

- `<h1>` with the stockist name, a real `<address>`, a `tel:` link and a Google Maps link
- `Store` JSON-LD: name, url, address, telephone, geo, `openingHours`, `hasMap`, image
- Breadcrumbs, and a link back to `/stockists`
- Per-record meta title / description / keywords via `website.seo.metadata`

The index emits `ItemList` JSON-LD for the current page.

**Every stockist link is a server-rendered `<a href>`.** No JavaScript map builds the list.
That is deliberate: the finding behind `TODO/P0-ship-today/42-stockist-reclamation.md` is
that only 3 of 103 brand dealer locators emit a crawlable link at all. A map can be added
on top later, but it must never be the only route to a stockist.

## Pulling the address from Google

Rather than typing an address twice and letting it drift, press **Fetch from Google** on
the stockist form. It calls the Places API (New), then shows a **diff** — what the site
holds beside what Google holds — with tick boxes for address, phone, opening hours,
coordinates, **website** and **photo**. **Nothing is written until you press Apply.**

That is deliberate. Of the 8 BrightEyes stores whose website and Google addresses disagree,
some are formatting but Rockhampton's Google address names a **different suburb**. A silent
overwrite would change how a store is described with nobody reading it.

Two more guards: a field Google has no value for is never blanked, and a place Google marks
`CLOSED_PERMANENTLY` or `CLOSED_TEMPORARILY` raises a banner before you can apply.

### Logo and photo are two different things

A stockist has two image fields and they are not interchangeable:

| Field | What it is | Where it renders | Filled by |
|---|---|---|---|
| **Logo** | the brand mark | 64px high beside the name, `width:auto` | you |
| **Photo** | the shopfront or interior | the right-hand column, capped at 420px high | Google, or you |

A logo dropped into **Photo** renders at the full width of a five-column block, which is why
a large upload looked enormous. Both are now served through `/web/image/.../<field>/WxH`, so
the file you upload is resized on the way out and its dimensions no longer decide the layout.

The photo comes from the listing's first Places photo, which is normally the shopfront. The
sync **only ever fills an empty photo, or replaces one a previous sync put there** —
`image_source` records which, and a photo you uploaded by hand is never overwritten. Google
bills per photo fetch, so the wizard decides whether it would apply one *before* it downloads
anything.

In the page's Store JSON-LD they stay separate: the photo is `image`, the logo is `logo`.
Google reads those as different claims, and a shopfront photo in the logo slot is worse than
no logo at all.

### Website

`websiteUri` was always in the field mask and was being thrown away. It now maps to
**Website** (`stockist_url`) — the link on the page and `sameAs` in the JSON-LD. Read it
before applying: for a chain, Google often holds the national site rather than the branch.

### Setup

1. Enable **Places API (New)** on Cloud project `organic-edge-501303-c7`.
2. Create an API key, restrict it to that API.
3. Settings → Technical → System Parameters → new parameter
   `website_stockist.google_places_api_key` = the key.

### When Google returns no street

Some listings ship the street line as an address component with **no `types` array at
all** — Stockland Rockhampton returns `{"longText": "331 Yaamba Road"}` and nothing else.
A lookup by `street_number` and `route` then finds neither, and the wizard offers a blank
address, which reads exactly like a listing with no street on it.

The parser now falls back twice when typed parsing yields nothing: first to the part of
`formattedAddress` that precedes the suburb (preferred, because it keeps the shop number
and centre name — "Shop 96 Stockland Rockhampton, 331 Yaamba Road" rather than a bare
"331 Yaamba Road"), then to untyped components appearing before the locality. Neither
fallback runs when Google types the address properly, so every listing that already
parsed is unaffected.

### About the identifier

`store-codes.csv` holds **CIDs**, and Google does not officially convert a CID to a place
id. The first fetch on a stockist with no `google_place_id` therefore runs a text search on
name + address and stores the resulting place id, so every later fetch is a direct lookup.
Check the matched name in the wizard on that first run — a text search can match the wrong
business.

### Terms of service

Google allows caching `place_id` indefinitely, but other Places content for **30 days**.
`google_sync_date` records when each stockist was last pulled.

For the group's own stores that restriction does not apply, and the **Business Profile API**
is the better source — richer data, no caching limit, and it is your own record rather than
Google's public copy. It needs OAuth plus an access application to Google, which is the slow
part; worth applying for in parallel. This module is Places-first precisely so nothing waits
on that queue.

## Sitemap

Published stockists appear in `/sitemap.xml` for every website they are assigned to, via
the `sitemap=` callback on the index route. Paginated pages are excluded.

## Fields worth knowing

| Field | Note |
|---|---|
| `ownership` | corporate / franchise / independent / online. Franchise and independent listings may not be ours to edit — recorded so nobody edits a listing they do not own. |
| `store_code` | Unique. For BrightEyes stores this is the Neto warehouse code (101 = Cairns Earlville). Blank codes are stored as NULL so two blanks do not collide. |
| `brand_ids` | Many2many to `product.tag`, which already holds brand-shaped tags here (`MJ`, `WYN`, `Rocko's`). Only name a brand the stockist genuinely carries. |
| `google_place_id` | Builds a stable Maps link and reconciles against Google Business Profile. |
| `opening_hours` | One line per day. Rendered verbatim and emitted as `openingHours`. Blank lines are dropped. |
| `canonical_website_id` | See above. |

`action_geolocate` fills latitude/longitude from the address using `base_geolocalize`.

## The 27 BrightEyes stores

`MJ/data/stores.json` holds all 27 — name, address, per-store phone, `/d/` URL, ownership,
store code and GBP CID.

This section previously said the import was blocked because `address_of_record` was unresolved and
8 corporate stores published a different street address on the website than on Google Business
Profile. **That was resolved on 27 Aug 2026 and this section was not updated** — it misled a reader
on 7 Sep who took it at face value.

The decisions, from `MJ/README.md`:

* **The store-finder page is the correct address.** `address_of_record` is set on all 27 records,
  parsed from the live `/d/` page string into street / suburb / state / postcode plus a single
  `formatted` citation line.
* **Where the store-finder and GBP disagree, GBP is what gets edited**, not the website. All eight
  are resolved and no `address_conflict` records remain — the last two, Gateway Palmerston and
  Karratha City, were verified against a rendered `google.com/maps?cid=` page on 7 Sep 2026 and both
  already carry the street number. The `gbp_address` field is not a safe baseline: it was captured
  from DataForSEO, which drops street numbers in favour of cross-street strings.
* **For the four unusable strings, GBP's street is used**, keeping the shop number and centre name
  from the store-finder because GBP mangles them ("Shop 070 T111", "Shop 184/13").

So the import is a straightforward load from that file. Verified 7 Sep 2026:
`address_of_record` populated on 27 of 27, ownership 24 corporate + 3 franchise.

### Importing them

`data/brighteyes_stores.csv` is that load, built by merging `MJ/data/stores.json` (identity,
`address_of_record`, ownership, store code, phone) with the store-finder scrape of 7 Sep 2026
(email and opening hours, which the JSON does not carry).

It is **not** in the manifest. Stockist records are business data that staff edit, and a
manifest data file is reloaded on every module update, silently reverting those edits.
Import it once instead: **Website → Configuration → Stockists → ⚙ → Import records**. The
`id` column carries an external id per store, so a corrected re-import updates the record
rather than creating a second one.

Ownership is 24 corporate + 3 franchise, from the JSON. The three franchises — North Lakes,
Sugarland Bundaberg and Broome Boulevard — are also the three with no Neto store code, so
`store_code` is blank for them; blank is stored as NULL and three blanks do not collide.

`website_ids` is absent from the file, which means every stockist publishes on all seven
websites. If these belong on one site only, add that column before importing.

Two gaps the file cannot fill: **Stockland Townsville publishes no email** and none was
invented, and **Castletown uses `@brighteyes.com.au`** where every sibling uses `.net.au`,
kept verbatim in case it is a typo worth fixing at source. Postcodes 0800, 0810, 0830 and
0870 carry a leading zero — do not round-trip the file through Excel, which drops it.

### The logo on every store

`static/src/img/brighteyes_logo.png` is the wordmark from `brighteyes.com.au`, shipped in the
module so it is version-controlled rather than re-uploaded per store.

Tick the stores in the list and press **Set BrightEyes logo** in the bar above it; the form
has the same button, shown only while that stockist has no logo. Both need the Website
Designer group, which is what holds write access here. The same action is bound to the ⚙
Actions menu.

It writes **`logo`**, never `image_1920` — see the table above for why those are not
interchangeable — and it **skips any stockist that already has a logo**, so a store with its
own brand mark keeps it. To replace one, clear it first and press again.

This leaves the shopfront photo empty on all 27. **Fetch from Google** fills that where the
listing has a photo.
