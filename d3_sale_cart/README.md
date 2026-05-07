# Abandoned Cart Coupon Generator for Odoo 18

This module enhances the standard *Website Sale* abandoned cart workflow by automatically generating and sending a discount coupon to customers who receive an abandoned checkout recovery email. It integrates with Odoo’s Loyalty Program system and adds new configuration options at the Website level.

---

## Features

### Automatic Coupon Generation
When an abandoned cart email is sent, the module can automatically:

- Generate a unique coupon for the customer.
- Use a selected *Loyalty Program* to create the coupon.
- Set a custom expiration period (in days).
- Insert the coupon code directly into the recovery email template.

### New Website Settings
A new configuration section is added under **Website → Settings → eCommerce**:

- Enable or disable coupon creation for abandoned cart emails.
- Select the Loyalty Program used to generate coupons.
- Define the number of days the coupon remains valid.

These settings are also exposed through `res.config.settings`.

### Sale Order Integration
Sale orders linked to a website with coupon generation enabled will automatically trigger:

- `action_generate_coupons()` — checks eligibility and generates coupons.
- `action_generate_coupon()` — creates the coupon, loyalty card, and history entry.

### Website Model Extension
The module adds three new fields to the `website` model:

- `create_coupon_abandoned_cart_email` (Boolean)
- `days_coupon_abandoned_cart_email` (Integer)
- `program_coupon_abandoned_cart_email` (Many2one to `loyalty.program`)

---

## Technical Overview

### Models Extended
- `res.config.settings`
- `sale.order`
- `website`

### Coupon Creation Logic
The coupon is generated using Odoo’s Loyalty Program engine:

- A `loyalty.generate.wizard` is instantiated.
- A loyalty card is created with `action_no_send_mail=True` to avoid default notifications.
- A loyalty history entry is recorded.
- The generated coupon code is returned and can be inserted into the email template.

---

## Required Email Template Modification

To display the generated coupon inside the abandoned cart recovery email, you **must modify** the following template:

### Template to edit
`mail_template_sale_cart_recovery`  
(from module: **website_sale**)

### Add this block inside the email body
```xml
<t t-if="object.website_id.create_coupon_abandoned_cart_email">
    <div style="background-color: #FF6B35; color: white; padding: 18px; border-radius: 8px; text-align: center; margin: 25px 0; box-shadow: 0 4px 15px #ff6b35;">
        <div style="font-size: 15px; font-weight: 700; margin-bottom: 6px; text-shadow: 0 1px 2px #e66030;">
            ⏳ HURRY! Limited Time Offer
        </div>
        <div style="font-size: 13px; opacity: 0.95; font-weight: 500; margin-bottom: 8px;">
            Complete your purchase within the next <strong>24 hours</strong> and get <strong>10% OFF</strong>.
        </div>
        <div style="font-size: 14px; font-weight: 600; background-color: #ffffff; color: #FF6B35; display: inline-block; padding: 6px 12px; border-radius: 5px;">
            Code: <strong t-out="object.action_generate_coupon() or ''">COUPON-CODE</strong>
        </div>
    </div>
</t>
