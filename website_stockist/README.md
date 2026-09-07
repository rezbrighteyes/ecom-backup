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

### Ranges and the products in them

Mangrove Jacks is **one brand**; MJ59, MJ89, MJ49 and MJFoot are **ranges within
it**. The field was called `brand_ids` and said "Brands stocked", which was wrong on
both counts — it is now `range_ids`, "Ranges stocked". The m2m relation table and its
columns are unchanged (`website_stockist_product_tag_rel`), so every existing row
carried across without a migration.

Ticking a range no longer just prints its code. `product_ids` is computed from
`range_ids` and the page renders those products with their images, linked to their own
product pages.

**The filtering lives in the module, not in how you tag.** Nobody should have to keep
tags tidy so a public page stays honest — tag what is true about the product, and the
compute decides what is fit to show. Three filters:

| Filter | Why |
|---|---|
| `is_published` | a stockist page must never advertise something with no page to link to |
| `sale_ok` and `active` | an archived or non-sellable product keeps its tags and would otherwise reappear after being deliberately withdrawn |
| `website_id` | `is_published` is **one boolean for the whole database**, not one per site — without this, a product published only on another site in the group would be offered by a Mangrove Jacks page |

The five ranges hold **299 published products** between them, so which ones show matters
more than how many. Products are drawn evenly from each range in the merchandiser's own
`website_sequence` order, then topped up from the whole set if a range is thin. Sorting
by name instead would return 24 products all beginning with the same letter, all from
whichever range sorts first. The cap is `PRODUCT_DISPLAY_LIMIT` (24).

Because 24 of 299 needs an exit, each range badge links to `/shop?tags=<id>` and the
strip carries a "Browse the full range" link with every tag. Both forms were checked
against the live site — the multi-tag URL returns a different product set from a
single-tag one, so the parameter is genuinely honoured.

That is also what goes into `makesOffer` now. Previously the JSON-LD offered the tag,
so a parser was told the store sells a thing called "MJ59". It now offers each product
by name with its URL, which is a claim that means something.

The strip scrolls horizontally rather than auto-scrolling. A marquee moves a product
name out from under whoever is reading it and a touch user cannot pause one mid-read;
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

### Titles and meta descriptions

The title is written to `website_meta_title` on each record and follows one pattern:

```
Mangrove Jacks at BrightEyes Morayfield
Mangrove Jacks at Anaconda Rockdale
```

Measured against all 126 stockists it runs 32-60 characters and **never overruns 60**.
Four other patterns were measured and rejected: putting "Sunglasses" in the title
overruns on 13, "| Mangrove Jacks Stockist" on 7, and leading with the suburb produces
"Mangrove Jacks Banksia | Anaconda Rockdale" because a chain's store name and its
suburb frequently disagree.

Worth being honest about what this title is for. There is **no meaningful search
demand** to win here: "mangrove jack" is a fish (590/mo for fishing, 320 for lures,
nothing for the sunglasses brand), local retail demand is thin, and each retailer's own
store page already ranks for its own name. These pages exist to be the machine-readable
record that the brand is stocked in 126 named shops. So the title states that claim
rather than chasing a query.

**The description is computed, never written.** It is built from the stockist's ranges
through `stockist_category` on each tag, so a store that gets hats tagged next week
starts saying so without anyone editing 126 pages:

```
Find Mangrove Jacks sunglasses at BrightEyes Morayfield, Morayfield 4506.
Call (07) 5495 3133 to check what's in stock.

Find Mangrove Jacks sunglasses, hats and footwear at BrightEyes Morayfield,
Morayfield 4506. Call (07) 5495 3133 to check what's in stock.
```

Categories read in a fixed order (sunglasses, hats, footwear, apparel, accessories)
rather than whatever order the tags were ticked in. A range nobody has classified still
shows on the page and simply adds no word. Checked against all 127 records in every
combination: nothing exceeds 155 characters, and where four categories make the opening
too long the phone sentence shortens to "Call 07 xxxx xxxx." rather than dropping — the
number is the action, the invitation around it is not.

It is supplied through `_default_website_meta`, so anything typed into the SEO tab by
hand still wins. Set it there when a store deserves something specific.

**So the SEO tab reads as empty even though the page is right.** Only the title is stored
on the record; description, `og:description` and `twitter:description` are produced at
render. Odoo's "is SEO optimized" indicator reads the stored fields, so it will stay off.
That is the cost of a description that follows the ranges instead of freezing.

`og:image` and `twitter:image` are set to the stockist's own shopfront, falling back to
its logo. Without that, all 127 pages share one social image — the site logo — so every
shared link looks identical. With no image of its own the field is left unset and Odoo's
own fallback applies; duplicating that here would only be a second way to get it wrong.

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
