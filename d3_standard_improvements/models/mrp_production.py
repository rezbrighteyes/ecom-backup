# -*- coding: utf-8 -*-


from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    work_center_cost = fields.Boolean(default=True, copy=False)

    def get_mrp_cost_structures(self):
        Structure = self.env["report.mrp_account_enterprise.mrp_cost_structure"]
        structure = []
        lines = Structure.sudo().get_lines(self)
        for line in lines:
            operations = []
            ops = line.get('operations', [])
            for op in ops:
                operations.append({
                    'resource': op[0],
                    'operation': op[1] or op[2], # mrp.routing.workcenter
                    'time': op[3],
                    'cost': op[4],
                    'total': op[3] * op[4],
                })
            structure.append(
                {
                    "mo_qty": line.get('mo_qty'),
                    "total_cost_components": line.get('total_cost_components'),
                    "total_cost_operations": line.get('total_cost_operations'),
                    "total_cost": line.get('total_cost'),
                    "operations": operations
                }
            )
        return structure

    def get_mrp_cost_structure(self):
        Structure = self.env["report.mrp_account_enterprise.mrp_cost_structure"]
        mrp_cost = 0
        lines = Structure.sudo().get_lines(self)
        for line in lines:
            mrp_cost += line.get("total_cost_operations")
        return mrp_cost

    def get_work_center_cost(self):
        work_center_cost = 0
        for work_order in self.workorder_ids:
            work_center_cost += work_order._cal_cost()
        return work_center_cost

    def action_work_center_cost(self):
        if not self.company_id.work_center_cost:
            return False

        for order in self.filtered("work_center_cost"):
            finished_move = self.move_finished_ids.filtered(
                lambda x: x.product_id == order.product_id
                and x.state == "done"
                and x.quantity > 0
            )

            if not finished_move:
                continue

            svl = finished_move.stock_valuation_layer_ids
            if not svl:
                continue

            cost = order.get_mrp_cost_structure() or order.get_work_center_cost()
            if not cost:
                continue

            accounts_data = (
                finished_move.product_id.product_tmpl_id.get_product_accounts()
            )
            acc_expense = accounts_data.get("expense")
            acc_production = accounts_data.get("production")
            journal_id = accounts_data["stock_journal"].id

            am_vals = finished_move._prepare_account_move_vals(
                acc_expense.id,
                acc_production.id,
                journal_id,
                0,
                svl.description,
                svl.id,
                cost,
            )

            account_move = self.env["account.move"].sudo().create(am_vals)
            account_move._post()

            order.work_center_cost = False

        return True

    def _post_inventory(self, cancel_backorder=False):
        res = super(MrpProduction, self)._post_inventory(
            cancel_backorder=cancel_backorder
        )
        # self.action_work_center_cost()
        self.get_mrp_cost_structures()
        return res
