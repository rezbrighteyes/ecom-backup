# D3 Website Product Extended – Odoo 18

This module] = variantsThis module enhances Odoo’s eCommerce frontend by extending product variant rendering, modifying the shop controller logic, and introducing new UI components for a more advanced and flexible online shopping experience.

It is ideal for websites that require richer product variant displays, custom product grids, and extended filtering and search behavior.

---

## 🚀 Key Features

### 🎨 1. Enhanced Product Grid (Variants Display)
The module overrides `TableCompute.process()` to inject additional data into each grid cell:

- Displays **available variants** directly in the product grid.
- Uses the method `product_template.get_selected_variants()` to load variant options dynamically.
- Prepares each frontend grid cell with:
  ```python
