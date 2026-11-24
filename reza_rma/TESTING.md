# Reza RMA — Testing Guide

This guide covers end-to-end testing of the returns module from both the customer portal side and the staff backend side. Work through every section in order. Each section lists what you expect to see — if anything looks different, note it down.

---

## Before You Start

You need two browser sessions open at the same time:
- **Session A — Staff:** logged in as an Odoo backend user (Sales Manager or Administrator)
- **Session B — Customer:** logged in as a portal user who has at least one confirmed sale order

If you do not have a portal user with a sale order, create one first:
1. In the backend, open any confirmed sale order
2. Go to the customer on that order → Action → Grant portal access
3. The customer will receive a login email — or set their password manually via Settings → Users

---

## Part 1 — Portal Home Tile

**In Session B (customer browser)**

1. Go to `/my/home`
2. You should see a **Returns** tile
3. The tile should show a number (0 if no returns exist yet, or the correct count if they do)
4. The old **RMA Orders** tile from OCA should NOT appear — only our **Returns** tile
5. Click the tile — it should take you to `/my/rmas`

**Pass criteria:** Returns tile visible with correct count, no duplicate OCA tile.

---

## Part 2 — Portal Returns List (Empty State)

**In Session B**

1. Go to `/my/rmas`
2. If the customer has no returns yet, you should see:
   - The message "You have no return requests."
   - A **Start a Return** button
3. Click **Start a New Return** (top right button) — should go to `/my/rmas/new`

**Pass criteria:** Empty state shows correctly, button navigates to create form.

---

## Part 3 — Create Form — Order Window Enforcement

**In Session B**

1. Go to `/my/rmas/new`
2. The **Which order are you returning?** dropdown should only show orders placed within the last 30 days
3. If the customer has an order older than 30 days, confirm it does NOT appear in the list
4. If the customer has NO eligible orders (all older than 30 days), you should see the message:
   > "You have no orders eligible for a return. Orders must be within 30 days of purchase."
   and no form should appear

**Pass criteria:** Ineligible orders are excluded, correct message shown when none eligible.

---

## Part 4 — Create Form — Validation

**In Session B** (assumes at least one eligible order exists)

Go to `/my/rmas/new` and test each validation:

### 4a — Submit empty form
1. Click **Submit Return Request** without filling anything
2. You should see error messages appear — at minimum "Please select a valid return reason" and "Please select a return outcome"

### 4b — Reason requiring photo attachment
1. Select a reason that requires photos — **Defective / Faulty Item**, **Wrong Item Received**, **Damaged in Transit**, **Missing Parts / Incomplete**, or **Warranty Claim**
2. A photo upload section should appear automatically (this is JavaScript — no page reload)
3. Try to submit without uploading a photo
4. You should see: "Please upload at least one photo for this return reason."

### 4c — Reason NOT requiring photo
1. Select **Change of Mind** or **Wrong Size / Fit**
2. The photo upload section should disappear
3. Submitting without a photo should now succeed (if other fields are filled)

**Pass criteria:** All three validation scenarios behave as described.

---

## Part 5 — Successful Submission

**In Session B**

1. Fill in the create form completely:
   - Select an eligible order
   - Select any reason (use **Change of Mind** to avoid needing a photo)
   - Select an outcome — e.g. **Refund to original payment method**
   - Leave return method on **Australia Post** (default)
   - Tick at least one condition checkbox
   - Add a note in the text area (optional)
2. Click **Submit Return Request**
3. You should be redirected to the detail page at `/my/rmas/{id}`
4. A green success banner should appear at the top:
   > "Your return request has been submitted. Our team will be in touch within 1–2 business days."
5. The status badge should show **Submitted**
6. The detail page should show:
   - The correct sale order linked
   - The reason you selected
   - The outcome you selected
   - The return method
   - The submission date

**Pass criteria:** Redirect works, banner appears, all submitted data shows correctly.

---

## Part 6 — Confirmation Email

**In Session A (staff backend)**

1. Go to the RMA that was just created — find it under **RMA → Orders**
2. Open the RMA
3. In the chatter at the bottom, you should see the submitted confirmation email was sent (Odoo logs outgoing emails in the chatter)

**Alternatively:** Check the customer's email inbox — they should have received:
- Subject: "Your Return Request [RMA name] Has Been Received"
- Body: greeting, RMA reference, "within 1–2 business days", link to the portal

**Pass criteria:** Email sent and visible in chatter.

---

## Part 7 — Backend RMA Form — Return Details Tab

**In Session A (staff)**

1. Open the RMA from **RMA → Orders**
2. The form should show the standard OCA header and status bar
3. Click the **Return Details** tab
4. You should see:
   - **Customer Details** section: reason, requested outcome, return method, customer notes, damage flag
   - **SLA** section: Warehouse Received Date (blank), SLA Due Date (blank), SLA Alerted (unticked), Visible on Portal (ticked)
   - **Customer Declarations** section: the checkboxes the customer ticked
5. The **Inspection** section should not be visible yet (it only appears after an inspection is recorded)

**Pass criteria:** Tab visible, all customer data shown correctly.

---

## Part 8 — Staff Approval Workflow

**In Session A (staff)**

1. On the RMA, click **Confirm** (OCA button in header) — state moves to **Confirmed**
2. Check Session B — the portal detail page status badge should now show **Under Review**
   (refresh the page in Session B)
3. Back in Session A, click **Send Approval Email** (our button in the header)
4. The customer should receive one of two emails depending on return method:
   - **AusPost path:** Subject contains "Please Post Your Item", body includes link to returns.auspost.com.au
   - **Manual path:** Subject contains "Return Address Inside", body includes the company's warehouse address

**Pass criteria:** State changes, portal badge updates, approval email sent with correct content.

---

## Part 9 — Warehouse Receipt and SLA

**In Session A (staff)**

1. On the confirmed RMA, go to the **Return Details** tab
2. Set **Warehouse Received Date** to today's date and time
3. Save the record
4. **SLA Due Date** should automatically calculate to 2 days from now
5. Create a stock receipt via OCA's **Create Receipt** button (this creates the inbound picking)
6. Validate the picking — state should move to **Received**
7. Check Session B — portal badge should now show **Received by Warehouse**

**Pass criteria:** SLA date computes, state progresses, portal updates.

---

## Part 10 — Inspection Wizard

**In Session A (staff)**

1. On the received RMA, click **Record Inspection** (our button in the header)
2. A popup wizard should open with:
   - **RMA** field (read-only, pre-filled with this RMA)
   - **Inspection Outcome** dropdown (required)
   - **Inspection Notes** text area
3. Test the **Damaged / Used** path first:
   - Select **Damaged / Used — Return to Customer**
   - Add a note: "Item shows clear signs of use"
   - Click **Confirm**
   - The RMA should be **cancelled**
   - The customer should receive the damaged item email:
     Subject: "Update on Return Request [name] — Item Condition"
   - The **Return Details** tab should show the inspection outcome recorded

4. To test the **Acceptable** path, create a new test RMA and repeat Parts 5–9, then:
   - Click **Record Inspection**
   - Select **Acceptable — Condition Met**
   - Click **Confirm**
   - The **Create Credit Note** button should now be visible in the header
   - If outcome is **Exchange**, the **Create Exchange Order** button should also appear

**Pass criteria:** Wizard opens, both outcomes work correctly, emails sent, buttons appear/disappear correctly.

---

## Part 11 — Credit Note Creation

**In Session A (staff)** — requires an RMA with inspection outcome = Acceptable

1. Click **Create Credit Note**
2. A draft credit note should open, referencing "RMA [name]" in the reference field
3. Check the lines on the credit note:
   - Product lines should be present from the original invoice
   - Any line whose product name contains "shipping", "delivery", "freight", or "postage" should have **quantity = 0**
4. Review and post the credit note manually when ready

**If the button raises an error:** Confirm the linked sale order has a posted invoice. If there is no posted invoice, the button will raise "No posted invoice found."

**Pass criteria:** Credit note opens, freight lines are zeroed.

---

## Part 12 — Exchange Order Creation

**In Session A (staff)** — requires an RMA with inspection = Acceptable AND outcome = Exchange

1. Click **Create Exchange Order**
2. A new draft sale order should open for the same customer
3. The internal note should read: "Exchange for RMA [name] — original order [order name]"
4. Add the replacement product manually and confirm the order

**Pass criteria:** Draft sale order created with correct customer and note.

---

## Part 13 — Closing and Done Email

**In Session A (staff)**

1. Once the refund or exchange is processed, use OCA's workflow to finish the RMA (or use the close button if wired up)
2. The customer should receive the closed confirmation email:
   - Subject: "Return [name] — Processed"
   - Body varies by outcome type (refund / store credit / exchange)
3. Portal badge in Session B should now show **Closed**

**Pass criteria:** Done email sent with correct body for the outcome type.

---

## Part 14 — Customer Message Thread

**In Session B (customer portal)**

1. Open any RMA detail page that is not in Closed/Cancelled state
2. At the bottom, there should be a **Send a Message** text area
3. Type a message and click **Send Message**
4. The page should reload and the message should appear in the thread above

**In Session A (staff)**

5. Open the same RMA in the backend
6. The customer's message should appear in the Discuss chatter

**Pass criteria:** Message posted from portal appears in backend chatter.

---

## Part 15 — Portal Isolation Check

**Critical security test.**

1. Note the ID of the RMA created in Session B (visible in the URL: `/my/rmas/123`)
2. Log in as a **different portal user** (different customer account) in a third browser or incognito window
3. Try to access `/my/rmas/123` directly in the URL bar
4. You should be redirected to `/my` — access denied

**Pass criteria:** Customer cannot access another customer's RMA by guessing the URL.

---

## Part 16 — Product Return Method Default

**In Session A (staff)**

1. Open any product form
2. Click the **Sales** tab
3. You should see a **Returns** section with the **RMA Return Method** field
4. Change it to **Manual — Warehouse Address**
5. Save the product
6. In Session B, create a new return for an order containing that product
7. The **Return Method** on the new RMA should default to **Manual**

**Pass criteria:** Product-level default carries through to new RMAs.

---

## Part 17 — Return Reasons Management

**In Session A (staff)**

1. Go to **RMA → Configuration → Return Reasons**
2. You should see the 7 seeded reasons:
   - Defective / Faulty Item (requires photo)
   - Wrong Item Received (requires photo)
   - Damaged in Transit (requires photo)
   - Change of Mind (no photo required)
   - Wrong Size / Fit (no photo required)
   - Missing Parts / Incomplete (requires photo)
   - Warranty Claim (requires photo)
3. Create a new reason with **Customer Selectable** unticked
4. Go back to Session B and check the create form — the new reason should NOT appear in the dropdown

**Pass criteria:** Reason list correct, non-selectable reasons hidden from portal.

---

## Part 18 — SLA Cron (can be tested in developer mode)

**In Session A (staff — developer mode)**

1. Create a test RMA, set it to **Received** state, and set **Warehouse Received Date** to 3 days ago
2. Go to **Settings → Technical → Automation → Scheduled Actions**
3. Find **RMA: SLA Overdue Alert**
4. Click **Run Manually**
5. Go back to the RMA — there should be a new **Warning** activity on the record
6. The **SLA Alerted** checkbox in the Return Details tab should now be ticked
7. Run the cron again — no new activity should be created (it does not repeat)

**Pass criteria:** Activity created once on overdue RMAs, flag set, no duplicate alerts.

---

## Known Limitations (Phase 1)

These are intentional gaps — not bugs:

- No AusPost label generation — customers use the AusPost portal themselves
- No automated payment on credit notes — staff processes payment manually
- No product-level return window override — all products use the 30-day window
- No warranty period enforcement per product
- Exchange shipment tracking link not shown on portal

---

## If Something Goes Wrong

| Symptom | Where to look |
|---|---|
| Module won't install | Odoo.sh build log — check for Python import errors or XML parse errors |
| Portal tile missing | Confirm `reza_rma_count` is returned by `_prepare_home_portal_values` — check the controller is loaded |
| Create form not saving | Check browser network tab for the POST response — look for validation errors in the response body |
| Emails not sending | Check Settings → Technical → Email → Outgoing Mail Server is configured |
| Credit note button missing | Confirm inspection outcome is set to **Acceptable** on the Return Details tab |
| Wrong state badge on portal | Clear browser cache and hard-refresh — computed fields may be cached |
| "No posted invoice" error | The sale order needs a confirmed, posted invoice before credit note can be created |
