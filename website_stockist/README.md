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

### One shop, several brands — the per-website content model

A shop that stocks two of the group's brands appears on two sites. The shop is one thing —
one address, one phone, one set of hours — but what it sells and what it should say differ
per brand.

There are two ways to handle that and they are mutually exclusive:

| | Canonical to one owner | Per-website content |
|---|---|---|
| Duplicate content | eliminated | avoided, because the pages genuinely differ |
| Which site can rank | one | all of them |
| Setup | tick **Canonical website** | one content row per site |

`website.stockist.content` is the second. One row per website, holding:

* **the stockist tag** — the important one. It selects the products, and the products drive
  the categories, the strip and the generated description. A shop tagged for Rocko's on
  rockos.com.au and Mangrove Jacks on mangrovejacks.net.au produces different copy on each
  site with nobody writing any.
* **the brand name** used in the description and as `brand` in the Store JSON-LD. This was
  **hardcoded to "Mangrove Jacks"**, so every other site would have published a wrong claim
  in its structured data — worse than an absent one.
* optional title, description and body overrides for stores that earn something bespoke.

The address stays on the stockist and is maintained once. Address drift between sites is one
of the few things that genuinely damages local search, and duplicating this module per site —
the other obvious approach — guarantees it, as well as guaranteeing that a fix lands in one
copy and not the others.

**Adding a website is adding a row — and the module adds it for you.** Put a website in
`website_ids` and its content row appears, seeded from the record-level tag. Take the website
away and the row **stays**: the copy on it was written by a person, and a publishing change
is not consent to delete it.

**There is one place to set the tag, and it is the row.** The record still has
`stockist_tag_ids` as a fallback for anything written before this model existed, but it is no
longer editable on the form. Two fields setting one thing is how it gets set in the wrong
one — and a tag on the record applies to every site at once, which is precisely what the
per-website model exists to stop.

Every resolver takes an optional `website` and falls back to the record-level fields when
there is no row, so a stockist that predates the model keeps working. The 18.0.7.0.0
migration seeds a row per website for every existing stockist, carrying the tag across, so
behaviour does not silently change the first time somebody edits one.

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

### One tag per stockist decides what that stockist may show

`stockist_tag_ids` holds **the tag that names the stockist on a product** — `BER`,
`Anaconda`. Tag a product with it and that stockist may show the product; leave it off
and the product never appears on that page. Stockists carry different parts of the
range, and this is what keeps each page honest about which part.

It is a many2many, so a stockist can hold more than one tag, and the field has been
renamed twice (`brand_ids`, then `range_ids`) without ever moving data: an m2m is stored
by relation table, not by field name, so the table and its columns are unchanged.

`product_ids` is computed from it. **The filtering lives in the module, not in how you
tag.** Nobody should have to keep tags tidy so a public page stays honest — tag what is
true about the product, and the compute decides what is fit to show:

| Filter | Why |
|---|---|
| `is_published` | a stockist page must never advertise something with no page to link to |
| `sale_ok` and `active` | an archived or non-sellable product keeps its tags and would otherwise reappear after being deliberately withdrawn |
| `website_id` | `is_published` is **one boolean for the whole database**, not one per site — without this, a product published only on another site in the group would be offered by a Mangrove Jacks page |

The strip is capped at `PRODUCT_DISPLAY_LIMIT` (24) and drawn evenly across categories in
the merchandiser's own `website_sequence` order, then topped up if a category is thin.
Ordering by name instead would return 24 products all beginning with the same letter.

Because 24 of several hundred needs an exit, each category badge links to
`/shop?tags=<ids>` and the strip carries a "Browse the full range" link. Both forms were
checked against the live site — the multi-tag URL returns a different product set from a
single-tag one, so the parameter is genuinely honoured.

The strip scrolls horizontally rather than auto-scrolling. A marquee moves a product name
out from under whoever is reading it and a touch user cannot pause one mid-read;
scroll-snap gets the same compactness and stays under the reader's control.

### The page says Sunglasses, not MJ39

Nobody outside the business knows what MJ39 is. They know **Sunglasses**.

**Categories come from the products, not from the tags ticked on the stockist.** That
distinction matters because a retailer can be recorded either way:

* **By range** — a BrightEyes store ticked MJ39, MJ49, MJ59.
* **By retailer** — every product Anaconda carries is tagged `Anaconda`, and the
  stockist is ticked with that one tag.

In the second shape the tag on the stockist says nothing at all about the range. The
products do: each carries its own range tags, and those carry the category. Reading the
categories off the products handles both shapes with one rule, and keeps the page honest
either way — the badges cannot claim a category the stock does not support.

Two consequences worth knowing:

* **The strip samples by category, not by tag.** With one retailer tag, sampling by tag
  is one bucket, and 24 products in merchandising order are all sunglasses — a store
  that genuinely sells footwear and headwear would show none of it.
* **Categories describe everything stocked, not just the 24 shown.** A store with 400
  sunglasses and one shirt still gets an Apparel badge.

A category whose tags nobody has classified simply does not appear. Its products still
show in the strip, so nothing is lost from the page — publishing "MJMystery" to a
customer would be worse than publishing nothing. Find them with the **Needs a stockist
category** filter on the product tag list.

The category is **Headwear**, not "Hats": MJHat is one range of several, and the group
counts caps, beanies and visors in the same category.

The categories are sunglasses, headwear, footwear, apparel, **fishing tackle** and
accessories, and they read in that fixed order rather than the order tags were ticked.
Fishing tackle earns its own word: 288 distinct publishable products sit behind Lures,
Hooks, Jigs, Line & Tackle and the rest — close to the whole sunglasses catalogue — and
none of it is apparel or an accessory.

Two traps found while classifying, both of which a name-based guess would have got wrong:
**Stalkers** is clip-on sunglasses and **Obsession** is a sunglasses brand, so neither is
fishing despite sitting beside the tackle tags. **Fishing Apparel** is shirts and neck
gaiters, so it is apparel rather than tackle. Read a few product names before classifying
a tag.

### Titles and meta descriptions — generated, not stored

Both are **computed per website**, and neither is kept on the stockist record.

```
Mangrove Jacks at BrightEyes Morayfield        on mangrovejacks.net.au
Rocko's at BrightEyes Morayfield               on rockos.com.au
```

```
Find Mangrove Jacks sunglasses and footwear at BrightEyes Morayfield,
Morayfield 4506. Call (07) 5495 3133 to check what's in stock.
```

The title pattern was chosen by measuring five against all 126 stockists: it runs 32-60
characters and never overruns 60, where putting "Sunglasses" in the title overruns on 13 and
leading with the suburb produces "Mangrove Jacks Banksia | Anaconda Rockdale", because a
chain's store name and its suburb frequently disagree.

**Why generated rather than stored.** 127 records were once written with
`website_meta_title = "Mangrove Jacks at <store>"`. That string is static, so on a second
brand's site every page would have carried the wrong brand — the same defect as the
hardcoded brand in the JSON-LD, sitting in data instead of code. It also could not be
overridden: `website.layout` prefers a stored `website_meta_title` to anything computed, so
it would have silently beaten the generator. The 18.0.9.0.0 migration clears the ones this
module generated and leaves anything hand-written alone.

The title reaches the page through the render context rather than the record, because
`website.layout` only computes a title when the context has not already supplied one.

**Where to put a bespoke title or description:** the per-website content row. That is the
only place a hand-written string belongs, because it is the only place that knows which site
it is for.

Descriptions read in a fixed category order — sunglasses, headwear, footwear, apparel,
fishing tackle, accessories — rather than the order tags were ticked, and a range nobody has
classified adds no word. Checked against all 127 records in every combination: nothing
exceeds 155 characters, and where four categories leave no room the phone sentence shortens
to "Call 07 xxxx xxxx." rather than being dropped, because the number is the action.

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

## Become a stockist

Every stockist page carries an invitation, and the wording is **per website** —
Website > Configuration > Settings > Stockists. "Become a stockist", "Stock Rocko's",
"Wholesale enquiries": whatever suits that brand. The same sentence on five sites is what
makes a group of brands read as one template.

**Three labels, all per website, all independent:** the button on the stockist pages, the
`<h1>` on the application page, and the submit button. They are separate because a button
says what to do and a heading says what the page is — reusing one string for both put
"Click here to start selling Mangrove Jacks" in an `<h1>`, an instruction addressed to
nobody.

The call to action uses the theme's own CTA classes (`btn btn-primary btn_cta`) and the
submit uses its form-send style (`btn btn-secondary`), so the form looks like the rest of the
site rather than like Bootstrap's defaults.

`/stockists/apply` takes the application and creates a **helpdesk ticket** on the team that
belongs to that site. Routing tries three things in order:

1. the team set explicitly in settings
2. a team whose `website_id` is this website
3. a team whose `company_id` is this website's company

Step three is the one that resolves today: only two of the seven teams carry a `website_id`,
while every brand site has its own company and its own Customer Care team. If none of the
three finds a team the submission is **logged as an error rather than silently dropped** — a
retailer who fills in a form and hears nothing has been told the brand does not want them.

**Spam defence is layered, because reCAPTCHA is not configured on this database.** A honeypot
field and the required-field checks work with no setup at all; the reCAPTCHA check is wired
in and joins automatically if keys are ever added. Odoo returns `no_secret` when the keys are
unset, and that is treated as a pass — treating it as a failure would reject every genuine
application on a database that has never had keys.

The form page is indexable on purpose. "Become a stockist" and wholesale enquiries are real
B2B searches, and this is the page that answers them.

## Sitemap

Published stockists appear in `/sitemap.xml` for every website they are assigned to, via
the `sitemap=` callback on the index route. Paginated pages are excluded.

Each entry carries a **`lastmod`** from the stockist's `write_date`. Odoo emits `lastmod`
for `website.page` records and nothing else — on the Mangrove Jacks site that was 3 URLs
out of 556 — and `lastmod` is the signal Google reads to decide whether a page is worth
recrawling. `priority` and `changefreq` are deliberately not set: the template supports
them and Google ignores both.

**Odoo caches the sitemap as an attachment for 12 hours**, named `/sitemap-<website
id>-<hash>.xml`. So a newly installed module's pages do not appear until that expires,
and the sitemap you fetch can be older than the code. Mangrove Jacks is website 3. To
force a rebuild, delete its cached attachments:

```python
env["ir.attachment"].search([("name", "like", "/sitemap-3-")]).unlink()
```

Odoo never cleans these up — there were 39 on this database going back to May 2025, one
of them 600KB.

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
