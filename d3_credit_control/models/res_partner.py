# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.tools import SQL


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _default_credit_control(self):
        return self.env.company.credit_control

    def _default_overdue_control(self):
        return self.env.company.overdue_control

    credit_control = fields.Boolean(
        string="Credit Limit Block",
        default=_default_credit_control,
        tracking=True,
        help="Blocking customer due to credit limit",
    )

    overdue_control = fields.Boolean(
        string="Overdue Invoice Block",
        default=_default_overdue_control,
        tracking=True,
        help="Blocking customer due to overdue invoices",
    )

    credit_due = fields.Monetary(
        compute="_compute_credit_due",
        string="Total Overdue Receivable",
        groups="account.group_account_invoice,account.group_account_readonly",
    )

    @api.depends_context("company")
    def _compute_credit_due(self):
        if not self.ids:
            # self.debit = False
            self.credit_due = False
            return
        query = self.env["account.move.line"]._where_calc(
            [
                ("parent_state", "=", "posted"),
                ("company_id", "child_of", self.env.company.root_id.id),
            ]
        )
        self.env["account.move.line"].flush_model(
            [
                "account_id",
                "amount_residual",
                "company_id",
                "parent_state",
                "partner_id",
                "reconciled",
                "date_maturity",
            ]
        )
        self.env["account.account"].flush_model(["account_type"])
        sql = SQL(
            """
            SELECT account_move_line.partner_id, a.account_type, SUM(account_move_line.amount_residual)
            FROM %s
            LEFT JOIN account_account a ON (account_move_line.account_id=a.id)
            WHERE a.account_type IN ('asset_receivable','liability_payable')
            AND account_move_line.partner_id IN %s
            AND account_move_line.reconciled IS NOT TRUE
            AND %s
            AND account_move_line.date_maturity < %s
            GROUP BY account_move_line.partner_id, a.account_type
            """,
            query.from_clause,
            tuple(self.ids),
            query.where_clause or SQL("TRUE"),
            fields.Date.context_today(self).strftime('%Y-%m-%d')
        )
        treated = self.browse()
        for pid, account_type, val in self.env.execute_query(sql):
            partner = self.browse(pid)
            if account_type == "asset_receivable":
                partner.credit_due = val
                if partner not in treated:
                    # partner.debit = False
                    treated |= partner
            elif account_type == "liability_payable":
                # partner.debit = -val
                if partner not in treated:
                    partner.credit_due = False
                    treated |= partner
        remaining = self - treated
        # remaining.debit = False
        remaining.credit_due = False
