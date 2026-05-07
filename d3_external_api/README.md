# D3 External API – Odoo 18

D3 External API is an advanced integration module for synchronizing data between two separate Odoo instances using XML‑RPC.  
It allows automatic exchange of products, stock, purchase orders, sales orders, and inventory movements between a *local Odoo* and an *external Odoo database*.

---

## 🚀 Key Features

### 🔗 1. XML‑RPC External Connection
The module defines a service (`external.api`) that:
- Connects to a remote Odoo instance using XML‑RPC
- Validates the connection and credentials
- Fetches the list of remote companies
- Provides a reusable proxy for XML‑RPC calls:
  - Authentication
  - Search / Read / Write / Create

Includes a **Connection Check Wizard** to ensure configuration is valid.

---

### 📦 2. Product Synchronization
Imports and updates products from the external Odoo instance:

#### Supported Features:
- Templates
- Variants
- Attributes & attribute values
- Product categories (auto‑created if needed)
- Remote–local relationship via `external_api_id`
- Product fields synchronization (name, descriptions, UoM, codes, etc.)
- Price synchronization
- Images (`product.image`) import with variant/template assignment
- Optional filtering by creation date

Remote product IDs are written back to ensure bidirectional mapping.

---

### 🧩 3. Purchase → External Sale Synchronization
When a purchase order has **No Sync (external_api)** enabled:

#### On confirm:
- Creates a **Sale Order** in the external database
- Creates **Sale Order Lines**
- Confirms the remote sale
- Validates stock pickings if available
- Retrieves remote picking state to mirror inventory

#### On quantity change:
- Updates the remote sale order line
- Updates related remote stock moves
- Automatically validates external pickings

#### On cancel / draft / invoice:
- Cancels the remote sale
- Returns to draft
- Creates invoices via `sale.advance.payment.inv`

This ensures both instances remain aligned.

---

### 📦 4. Stock Quant Synchronization
Imports stock quants from the external Odoo instance:

- Matches remote quants to products using `external_api_id`
- Falls back to matching by `default_code` when needed
- Writes quants to a configurable local location
- Applies inventory adjustments
- Assigns inventory owner based on configuration

#### Automatic Reordering Logic:
- Products with **>5 units**:  
  - Allow out‑of‑stock orders  
  - Enable MTO route  
- Products with **≤5 units**:  
  - Disable out‑of‑stock orders  
  - Remove MTO route  

Uses product tags to exclude specific items from automated stock rules.

---

### 🏢 5. Company‑Level Configuration
Menu: **Settings → Company → External API**

Settings include:
- External URL
- Database name
- Username & password
- Enable/disable:
  - Product sync
  - Purchase sync
  - Quant sync
- External partner for remote sale creation
- Default location for external stock
- External partner for ownership of imported quants

---

## 📁 Module Structure

``