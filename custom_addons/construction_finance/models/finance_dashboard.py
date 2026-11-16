from odoo import api, fields, models, _


class ConstructionFinanceDashboard(models.TransientModel):
    _name = "construction.finance.dashboard"
    _description = "\u0424\u0438\u043d\u0430\u043d\u0441\u043e\u0432\u0430\u044f \u043f\u0430\u043d\u0435\u043b\u044c"
    _rec_name = "name"

    name = fields.Char(
        string="Название",
        compute="_compute_name",
    )

    def _compute_name(self):
        for record in self:
            record.name = _('Финансовая панель')

    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.ref("base.USD"),
        readonly=True,
    )

    date_from = fields.Date(
        string="From",
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string="To",
        default=fields.Date.context_today,
    )
    project_id = fields.Many2one(
        "construction.project",
        string="Project",
    )

    total_received = fields.Monetary(
        string="Received in Period",
        currency_field="currency_id",
        compute="_compute_dashboard",
    )
    total_debt = fields.Monetary(
        string="Outstanding Debt",
        currency_field="currency_id",
        compute="_compute_dashboard",
    )
    contract_count = fields.Integer(
        string="Active Contracts",
        compute="_compute_dashboard",
    )
    overdue_total = fields.Monetary(
        string="Overdue Balance",
        currency_field="currency_id",
        compute="_compute_dashboard",
    )
    payment_count = fields.Integer(
        string="Posted Payments",
        compute="_compute_dashboard",
    )

    overdue_count = fields.Integer(
        string="Overdue Installments",
        compute="_compute_dashboard",
    )

    @api.depends("date_from", "date_to", "project_id")
    def _compute_dashboard(self):
        Payment = self.env["construction.payment"]
        Plan = self.env["construction.payment.plan"]
        Schedule = self.env["construction.payment.schedule"]

        for dashboard in self:
            payment_domain = [("state", "=", "posted")]
            plan_domain = [("state", "in", ["confirmed", "closed"])]
            overdue_domain = [("state", "=", "overdue")]

            if dashboard.project_id:
                payment_domain.append(
                    ("project_id", "=", dashboard.project_id.id)
                )
                plan_domain.append(
                    ("project_id", "=", dashboard.project_id.id)
                )
                overdue_domain.append(
                    ("project_id", "=", dashboard.project_id.id)
                )

            if dashboard.date_from:
                payment_domain.append(
                    ("payment_date", ">=", dashboard.date_from)
                )
            if dashboard.date_to:
                payment_domain.append(
                    ("payment_date", "<=", dashboard.date_to)
                )

            payments = Payment.search(payment_domain)
            plans = Plan.search(plan_domain)
            overdue_lines = Schedule.search(overdue_domain)

            dashboard.total_received = sum(payments.mapped("amount_usd"))
            dashboard.payment_count = len(payments)
            dashboard.total_debt = sum(plans.mapped("balance_usd"))
            dashboard.contract_count = len(plans)
            dashboard.overdue_total = sum(
                overdue_lines.mapped("balance_usd")
            )
            dashboard.overdue_count = len(overdue_lines)

    def action_refresh(self):
        self.invalidate_recordset()
        self._compute_dashboard()
        return {
            "type": "ir.actions.act_window",
            "name": _("\u0424\u0438\u043d\u0430\u043d\u0441\u043e\u0432\u0430\u044f \u043f\u0430\u043d\u0435\u043b\u044c"),
            "res_model": "construction.finance.dashboard",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_open_payments(self):
        self.ensure_one()
        domain = [("state", "=", "posted")]
        if self.date_from:
            domain.append(("payment_date", ">=", self.date_from))
        if self.date_to:
            domain.append(("payment_date", "<=", self.date_to))
        if self.project_id:
            domain.append(("project_id", "=", self.project_id.id))
        return {
            "type": "ir.actions.act_window",
            "name": _("Posted Payments"),
            "res_model": "construction.payment",
            "view_mode": "list,form",
            "domain": domain,
        }

    def action_open_debts(self):
        self.ensure_one()
        domain = [("state", "in", ["confirmed", "closed"])]
        if self.project_id:
            domain.append(("project_id", "=", self.project_id.id))
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Debts"),
            "res_model": "construction.payment.plan",
            "view_mode": "list,form",
            "domain": domain,
        }

    def action_open_overdue(self):
        self.ensure_one()
        domain = [("state", "=", "overdue")]
        if self.project_id:
            domain.append(("project_id", "=", self.project_id.id))
        return {
            "type": "ir.actions.act_window",
            "name": _("Overdue Payments"),
            "res_model": "construction.payment.schedule",
            "view_mode": "list",
            "domain": domain,
        }


    def action_open_payments_graph(self):
        self.ensure_one()
        domain = [("state", "=", "posted")]
        if self.date_from:
            domain.append(("payment_date", ">=", self.date_from))
        if self.date_to:
            domain.append(("payment_date", "<=", self.date_to))
        if self.project_id:
            domain.append(("project_id", "=", self.project_id.id))
        return {
            "type": "ir.actions.act_window",
            "name": _("Monthly Payment Analysis"),
            "res_model": "construction.payment",
            "view_mode": "graph,pivot,list",
            "domain": domain,
            "context": {"search_default_group_by_payment_date": 1},
        }

    def action_open_debt_graph(self):
        self.ensure_one()
        domain = [("state", "in", ["confirmed", "closed"])]
        if self.project_id:
            domain.append(("project_id", "=", self.project_id.id))

        graph_view = self.env.ref(
            "construction_finance.view_finance_debt_project_graph"
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Debt by Project"),
            "res_model": "construction.payment.plan",
            "view_mode": "graph,pivot,list",
            "views": [
                (graph_view.id, "graph"),
                (False, "pivot"),
                (False, "list"),
            ],
            "domain": domain,
        }
