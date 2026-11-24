"""Odoo 20 helpers for partial returns and scraps.

Odoo 20 deleted the `stock.return.picking` wizard and the `stock.scrap`
model. A return is now `picking._create_return()`, which makes a DRAFT
picking whose moves start at zero; a scrap is a `stock.move` with
`is_scrap` set, sent to the company's scrap location.
"""

from odoo import _
from odoo.exceptions import UserError


def draft_return(picking):
    """Draft return of `picking`, each move preset to what can still be
    returned (`action_return_all`: the original done quantity less anything
    already returned). Callers lower `product_uom_qty` where they return
    less, then call `confirm_return`."""
    ret = picking._create_return()
    ret.action_return_all()
    return ret


def confirm_return(ret):
    """Drop the moves left at zero, then confirm and reserve the return.

    Returns the picking, or an empty recordset when nothing is left."""
    zero = ret.move_ids.filtered(lambda m: m.uom_id.is_zero(m.product_uom_qty))
    zero.unlink()
    if not ret.move_ids:
        ret.unlink()
        return ret.browse()
    ret.action_confirm()
    ret.action_assign()
    return ret


def validate_return(ret, what):
    """Mark every move done for its full quantity and validate."""
    for move in ret.move_ids:
        move.quantity = move.product_uom_qty
        move.picked = True
    ret.with_context(skip_backorder=True).button_validate()
    if ret.state != "done":
        raise UserError(_("%(what)s %(ret)s came back %(state)s.",
                          what=what, ret=ret.name, state=ret.state))
    return ret


def scrap(env, product, qty, location, company, origin):
    """Scrap `qty` (in the product's own unit) out of `location`, done.

    The destination is the company's scrap location (computed by the move),
    which on ecom carries the stock write-off accounts."""
    move = env["stock.move"].with_context(default_is_scrap=True).create({
        "product_id": product.id,
        "product_uom_qty": qty,
        "quantity": qty,
        "uom_id": product.uom_id.id,
        "location_id": location.id,
        "company_id": company.id,
        "origin": origin,
        "is_scrap": True,
    })
    move.action_scrap()
    if move.state != "done":
        raise UserError(_("Scrap of %s did not complete. Nothing was changed.",
                          product.display_name))
    return move
