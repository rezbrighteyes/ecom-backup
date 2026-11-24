# Reza RMA

Customer returns portal and policy enforcement for Odoo 18, built on top of OCA `rma` + `rma_sale`.

---

## What This Module Does

`reza_rma` gives customers a self-service returns portal and gives staff a
request-level workflow that groups item RMAs under one return reference, parcel,
label, policy snapshot, and financial summary.

### Customer-facing
- Dedicated portal at `/my/rmas` — list all their return requests with status badges
- Create a new return from `/my/rmas/new` — order selection (30-day window enforced), reason, preferred outcome (refund / store credit / exchange), return method, condition declarations, photo upload
- Track return status in real time
- Send messages to staff directly from the portal
- Receive automatic emails at every stage

### Staff-facing
- New **Return Details** tab on every RMA form in the backend
- **Record Inspection** button opens a wizard to log inspection outcome
- **Return Requests** operational screen groups all item RMAs for one parcel
- Scoped credit notes use OCA item-level RMA refund preparation; complete invoice reversal is disabled
- Exchange orders require an exact replacement variant and are dispatch-blocked until receipt, inspection pass, and payment where required
- Secure guest links use random request tokens; customer email is never placed in tracking or label URLs
- Failed label attempts are visible, retryable, and create staff activities
- **Send Approval Email** button sends return shipping instructions to the customer
- SLA tracking: 2-business-day deadline from warehouse receipt, with an automatic activity alert when overdue
- Per-product return method default (AusPost or manual address)

### Automated emails (6 templates)
| Trigger | Email sent |
|---|---|
| Customer submits portal form | Submission confirmation |
| Staff clicks Send Approval Email (AusPost path) | Approval + AusPost portal link |
| Staff clicks Send Approval Email (manual path) | Approval + company warehouse address |
| Inspection outcome = Damaged/Used or Missing Packaging | Item condition rejection |
| Staff refuses RMA manually | Rejection notice |
| Staff closes RMA | Processed / closed confirmation |

---

## Architecture

This module **does not fork OCA**. All code lives here as a pure extension.

| Layer | Provided by |
|---|---|
| RMA model, states, stock picking, refund creation | OCA `rma` (submodule at `/rma`) |
| Sale order link, RMA from sale order wizard | OCA `rma_sale` (submodule at `/rma`) |
| Request grouping, secure portal, policy, orchestration, inspection, SLA, reporting | `reza_rma` (this module) |

The OCA model is named `rma` (not `rma.rma`). All custom fields are prefixed `reza_` to avoid future OCA collisions.

---

## Installation

### Prerequisites
The OCA `rma` submodule must already be in the repo. Confirm with:
```
git submodule status
```
You should see a line for `rma` pointing to `heads/18.0`. If it is missing, run:
```
git submodule update --init --recursive
```

### Install order on Odoo
Install these three modules in this order. You can install them one at a time or let Odoo resolve the dependency chain by installing `reza_rma` directly (it will pull `rma` and `rma_sale` automatically).

**Recommended: install all at once**
1. Go to **Apps** → search `rma` → install **RMA** (OCA core)
2. Search `rma sale` → install **RMA Sale** (OCA sale link)
3. Search `reza rma` → install **Reza RMA** (this module)

If Odoo.sh is used, modules auto-discovered from the repo root — no manual addons path configuration needed.

---

## Post-Install Configuration

### 1. Create and configure the customer RMA Operation
OCA requires an operation type before an RMA can be confirmed.

**RMA → Configuration → Operations → New**

Minimum setup:
| Field | Value |
|---|---|
| Name | Return |
| Action: Create Receipt | checked |
| Action: Create Refund | Manually After Receipt for refund operations, otherwise blank |
| Action: Create Delivery | Manually After Receipt for replacement operations, otherwise blank |
| Auto-confirm Reception | Disabled |
| Location | Your warehouse return location |

Then select the appropriate operations under **RMA Settings → Refund / Store
Credit RMA Operation** and **Exchange RMA Operation**.

### 2. Keep feature flags disabled until staging sign-off

The module upgrades with automatic labels, scoped refunds, and exchanges disabled.
Enable each company feature flag only after its staging gate passes:

- **Enable Automatic Return Labels** after the existing Odoo 18 Starshipit runtime
  methods are available and a real return label passes staging testing. Do not
  activate the Odoo 19-marked app records on Odoo 18.
- **Enable Scoped Return Refunds** after accounting signs off partial-return totals.
- **Enable Exchanges** after stock reservation, payment, and dispatch gates pass.

Configure a service product with an income account as **Return Shipping Charge
Product** before enabling refunds.

### 3. Seed reason codes
Reason codes are seeded automatically on install (`noupdate="1"`):
- Defective / Faulty Item
- Wrong Item Received
- Damaged in Transit
- Change of Mind
- Wrong Size / Fit
- Missing Parts / Incomplete
- Warranty Claim

To manage them: **RMA → Configuration → Return Reasons**

### 4. Set product-level return method (optional)
For products that cannot use AusPost and require manual return shipping:

**Product form → Sales tab → Returns → RMA Return Method → Manual — Warehouse Address**

This default carries through to new RMAs created for that product.

### 5. Verify company address
The manual return address email template uses the company's registered address (`company_id.street`, `.city`, `.state_id`, `.zip`, `.country_id`). Confirm this is correct:

**Settings → Companies → your company → address fields**

### 6. Check scheduled actions
The cron job runs daily and creates an activity on any RMA that is overdue (2 days past warehouse received date).

Verify the SLA, guest lookup purge, and exchange hold expiry scheduled actions.
The failed-label retry cron remains disabled until Starshipit passes staging testing.

---

## Staff Workflow

### Receiving a return request

1. Customer submits form at `/my/rmas/new` → RMA created in **Draft** state
2. Staff receives submission confirmation email notification via Discuss
3. Open the grouped request from **RMA → Orders → Requests**
4. Review the **Return Details** tab for customer declarations, reason, requested outcome, and any uploaded photos
5. Click **Confirm** (OCA button) to move to **Confirmed** state
6. Click **Send Approval Email** to notify the customer with return shipping instructions

### After the item arrives at the warehouse

1. Set **Warehouse Received Date** in the Return Details tab — this starts the 2-day SLA clock
2. Click **Create Receipt** (OCA button) to record the stock move
3. Click **Record Inspection** to log the physical condition:
   - **Acceptable** → proceed to refund or exchange
   - **Damaged / Used** → RMA is cancelled, customer receives damaged-item email
   - **Missing Original Packaging** → RMA is cancelled, customer receives damaged-item email

### Processing an acceptable return

**Refund to original payment:**
1. Click **Create Scoped Credit Note** on the grouped request.
2. Review the draft credit note and its visible return-shipping charge.
3. Post only after checking selected quantities, tax, discounts, and currency.
4. Process the payment-provider refund manually until that provider is runtime verified.

**Store credit:**
1. Issue credit through the approved ecommerce-redeemable store-credit mechanism.
2. Record its reference on every request line.
3. Click **Confirm Store Credit Issued**.

**Exchange:**
1. Select the exact exchange product on each request line.
2. Record approved store credit first when the replacement is cheaper.
3. Click **Create Exchange Order**.
4. The order is confirmed to reserve stock. Its delivery cannot validate before
   receipt, inspection pass, and required payment.

### Closing
Click **Close** on the RMA (or use OCA's workflow) once everything is resolved. The customer receives a closed confirmation email.

### Manual rejection
At any point, use OCA's **Cancel** button to refuse the RMA. Then click **Send Approval Email** → actually use a manual chatter message, or the rejection email is sent automatically when inspection outcome is set to Damaged/Used.

To send a rejection email explicitly: open the RMA and call `reza_send_rejection_email` from the developer menu or wire a button — see developer notes below.

---

## Portal Workflow (Customer)

1. Customer logs in → sees **Returns** tile on `/my/home` with count
2. Clicks tile → `/my/rmas` shows all their return requests in a table with status badges
3. Clicks **Start a New Return** → `/my/rmas/new`
4. Selects an eligible order (only orders within 30 days of purchase appear)
5. Selects a return reason (reasons flagged `requires_attachment` trigger mandatory photo upload)
6. Selects preferred outcome and return method
7. Checks condition declarations and adds notes
8. Submits → redirected to detail page with success banner
9. Receives confirmation email immediately
10. Can message staff from the detail page at any time
11. Receives email updates as staff progress the RMA through states

### Portal status labels

| Backend state | Customer sees |
|---|---|
| Draft | Submitted |
| Confirmed | Under Review |
| Received | Received by Warehouse |
| Waiting for Return | Awaiting Return |
| Waiting for Replacement | Processing |
| Refunded | Processed — Refund Issued |
| Returned | Processed — Returned |
| Replaced | Processed — Exchange Sent |
| Finished / Locked | Closed |
| Cancelled | Cancelled |

---

## Business Rules Enforced in Code

| Rule | Where enforced |
|---|---|
| 30-day return window | Portal controller — orders outside window not shown in dropdown; secondary check on create |
| Remaining return quantity | Delivered quantity minus active request/legacy RMA quantities, rechecked under a row lock |
| Scoped credit note | OCA item-level refund preparation; complete-invoice reversal is not used |
| Return shipping deduction | Visible configured product line on the draft credit note |
| Financial/dispatch gate | Server blocks processing before warehouse receipt and passed inspection |
| Guest security | Rate-limited order/email lookup followed by random token-only URLs |
| Portal isolation by company and website | Controller checks both request company and website |
| Customer can only see their own RMAs | `_reza_get_rma_or_raise` checks commercial partner |

### Rules intentionally NOT enforced in code (staff decides manually)

- Whether a specific product is returnable
- Ray-Ban / Oakley security seal (BrightEyes)
- Edge cases and rejections → use OCA Cancel button
- Freight refund exceptions

---

## Multi-Website / Multi-Instance

The same module deploys to both **Ecom Superstore** and **BrightEyes** without code changes.

Isolation is by `company_id`. Each website has its own company, so portal customers on one site cannot see RMAs from the other.

Policy differences (Ray-Ban non-returnable, BrightEyes customer-pays-return-shipping) are handled by staff training, not code.

---

## Module File Reference

```
reza_rma/
├── models/
│   ├── rma.py                  — extends OCA rma with all reza_ fields + actions + email methods
│   ├── reza_rma_reason.py      — reason code model (reza.rma.reason)
│   └── product_template.py     — adds rma_return_method field to products
├── wizard/
│   └── reza_rma_inspect.py     — inspection wizard (reza.rma.inspect.wizard)
├── controllers/
│   └── portal.py               — all /my/rmas routes
├── views/
│   ├── rma_views.xml           — Return Details tab + action buttons on OCA form
│   ├── reza_rma_reason_views.xml — reason master data CRUD + RMA > Config menu
│   ├── reza_rma_inspect_views.xml — inspection wizard form
│   ├── product_template_views.xml — rma_return_method on product Sales tab
│   ├── portal_templates.xml    — /my/rmas list + detail QWeb
│   └── portal_rma_create.xml   — /my/rmas/new create form QWeb
├── data/
│   ├── reza_rma_reason_data.xml — 7 seeded reason codes (noupdate)
│   ├── mail_templates.xml      — 6 email templates
│   └── ir_cron.xml             — daily SLA overdue cron
├── security/
│   ├── ir.model.access.csv     — access for reza.rma.reason + inspect wizard
│   └── record_rules.xml        — (empty — portal access enforced in controller)
└── static/src/scss/
    └── portal_rma.scss         — portal form styles
```

---

## Developer Notes

### Adding the Rejection Email button to backend
The `reza_send_rejection_email` method exists but has no dedicated button in the backend view (staff typically cancel via OCA and the damaged email fires from the inspection wizard). To add a button, inherit `rma.rma_view_form` and add:
```xml
<button name="reza_send_rejection_email" string="Send Rejection Email" type="object" class="btn-secondary"/>
```

### Checking OCA state values
All OCA state values used in this module were confirmed against the installed `18.0` branch source:
`draft, confirmed, received, waiting_return, waiting_replacement, refunded, returned, replaced, finished, locked, cancelled`

There is no `refused` or `done` state in OCA 18.0.

### Runtime-dependent integrations
Starshipit tracking, payment-provider refunds, and ecommerce store-credit issuance
must be verified against the live staging registry and provider configuration.
Feature flags remain disabled until those checks pass.

### Portal URL conflict with OCA
OCA's own `PortalRma` controller also registers `/my/rmas`. Since `reza_rma` loads after `rma`, our `RezaRmaPortal` routes take precedence. The OCA portal tile ("RMA Orders") and our portal tile ("Returns") both appear on `/my/home` — both link to `/my/rmas` which our controller handles.
