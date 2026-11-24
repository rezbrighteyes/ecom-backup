# Reza RMA Runtime Verification

Run this checklist in staging before enabling any company feature flag.

## 1. Upgrade and Reconcile

Upgrade `reza_rma`, then run this read-only Odoo shell block:

```python
print("requests", env["reza.rma.request"].search_count([]))
print("request lines", env["reza.rma.request.line"].search_count([]))
print("rmas", env["rma"].search_count([]))
print("unlinked rmas", env["rma"].search_count([
    ("reza_request_line_id", "=", False),
    ("reza_migration_review_required", "=", False),
]))
print("migration review", env["rma"].search_read([
    ("reza_migration_review_required", "=", True),
], ["name", "order_id", "move_id", "picking_id"]))
print("operations", env["rma.operation"].search_read([], [
    "name", "action_create_receipt", "auto_confirm_reception",
    "action_create_refund", "action_create_delivery",
]))
```

Pass criteria:

- `unlinked rmas` is `0`.
- Every incomplete legacy RMA is listed under `migration review`.
- No operation uses automatic refund or automatic replacement delivery.
- Every operation has `auto_confirm_reception` disabled.

## 2. Runtime Integration Discovery

```python
for name in [
    "reza_rma", "rma", "rma_sale", "starshipit_delivery_carrier",
    "odoo_shipping_service_apps", "loyalty", "website_sale_loyalty", "payment",
]:
    module = env["ir.module.module"].search([("name", "=", name)], limit=1)
    print("MODULE", name, module.state, module.installed_version)

for model in [
    "loyalty.card", "loyalty.program", "payment.transaction",
    "delivery.carrier", "stock.picking",
]:
    print("MODEL", model, bool(env.registry.get(model)))
    if env.registry.get(model):
        print("FIELDS", model, sorted(env[model]._fields))
        print("METHODS", model, sorted(
            method for method in dir(env[model])
            if "refund" in method or "starshipit" in method or "payment" in method
        ))
```

The selected store-credit program must use `program_type = gift_card` and have
`ecommerce_ok` enabled. Do not search on `is_payment_program` because it is a
non-stored computed field in this runtime.

The Starshipit app records may show `uninstalled` because their manifests are
marked for Odoo 19 even though the existing Odoo 18 shipping code is loaded and
already creates labels/manifests. Do not activate those Odoo 19 app records.
Verify the live runtime exposes `delivery.carrier.starshipit_create_shipments`
or `delivery.carrier.starshipit_get_return_label`, then complete a real staging
return-label test before enabling automatic labels.

Each company must explicitly select its **Return Starshipit Carrier**. In this
staging database, the delivery-method UI can show Provider = Starshipit even
when searching stored `delivery_type = starshipit` returns no records. Select
the visible configured delivery method and rely on the loaded Starshipit
return-label method check. Never silently borrow a carrier belonging to another
website.

Do not enable scoped refunds until accounting signs
off partial quantities, discounts, tax-inclusive and tax-exclusive invoices,
return fees, multiple returns, and multi-currency. Providers without
`support_refund` remain manual. Do not enable exchanges until an outgoing
exchange picking is proven impossible to validate before receipt, inspection
pass, and required payment.

## 3. Required End-to-End Cases

1. Submit one guest partial return and confirm the URL contains only a random token.
2. Double-submit the same form and confirm only one request and RMA set exists.
3. Try returning more than the remaining delivered quantity and confirm rejection.
4. Try inspection before receipt and confirm rejection.
5. Try a refund and exchange before passed inspection and confirm no records are created.
6. Create a scoped credit note and reconcile every line and the visible return-shipping charge.
7. Force a label failure and confirm the request shows the error and staff activity.
8. Attempt cross-website token access and confirm no request or label is exposed.
9. Create an exchange with a positive difference and confirm delivery validation is blocked until payment is done.
10. Let an unpaid exchange hold expire and confirm the order cancels and stock releases.
