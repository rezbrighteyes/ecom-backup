D3 Credit Control
=================

This module extends Odoo to add customer blocking rules based on credit limits
and overdue invoices. It helps companies enforce credit policies directly
in **Sales Orders** and **Invoices**.

Features
========

- Adds company-level settings to enable or disable:
  
  - **Credit Limit Block**: Prevents confirmation of sales orders and posting of invoices
    if the customer exceeds the configured credit limit.
  - **Overdue Invoice Block**: Prevents confirmation of sales orders and posting of invoices
    if the customer has overdue receivables.

- Adds partner-level controls that inherit default values from the company
  but can be customized per customer.

- Computes and displays **Total Overdue Receivable** on the customer form.

- Integrates with:
  
  - **Sales Orders**: Blocks confirmation if conditions are met.
  - **Customer Invoices**: Blocks posting if conditions are met.

Configuration
=============

1. Go to **Invoicing > Configuration > Settings**.
2. Enable the options:

   - *Credit Limit Block*
   - *Overdue Invoice Block*

3. On each customer record, you can override these settings in the **Credit Limits**
   section.

Usage
=====

- When creating a **Sales Order** or an **Invoice**:
  
  - If the customer is marked with *Credit Limit Block* and their credit is exceeded,
    Odoo will raise a blocking error.
  - If the customer is marked with *Overdue Invoice Block* and has overdue receivables,
    Odoo will raise a blocking error.

Bug Tracker
-----------

Bugs are tracked on `GitHub Issues <https://github.com/TU_REPOSITORIO_GITHUB/issues>`_.
If you find a bug, please report it with detailed steps to reproduce the issue.

Credits
-------

Authors
~~~~~~~

.. image:: https://d-3system.com.au/wp-content/uploads/2020/05/Dimension3_Systems_460x159.png.webp
   :width: 25%
   :alt: Dimension 3 systems
   :target: https://d-3system.com.au/

Contributors
~~~~~~~~~~~~

* Juan Pablo Arcos

Maintainers
~~~~~~~~~~~

This module is maintained by your team or organization.

.. image:: https://d-3system.com.au/wp-content/uploads/2020/05/Dimension3_Systems_460x159.png.webp
   :width: 25%
   :alt: Dimension 3 systems
   :target: https://d-3system.com.au/

License
=======

Licensed under the LGPL v3.0 or later.  
This module is not part of an official OCA repository but follows OCA best development practices.
