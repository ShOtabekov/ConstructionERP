from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConstructionPaymentPlan(models.Model):
    _name = "construction.payment.plan"
    _description = "Construction Payment Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Plan Number",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )

    contract_id = fields.Many2one(
        "construction.contract",
        string="Contract",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )

    partner_id = fields.Many2one(
        related="contract_id.partner_id",
        string="Buyer",
        store=True,
        readonly=True,
    )

    apartment_id = fields.Many2one(
        related="contract_id.apartment_id",
        string="Apartment",
        store=True,
        readonly=True,
    )

    project_id = fields.Many2one(
        related="contract_id.project_id",
        string="Project",
        store=True,
        readonly=True,
    )

    currency_usd_id = fields.Many2one(
        "res.currency",
        string="USD Currency",
        default=lambda self: self.env.ref("base.USD"),
        readonly=True,
    )

    contract_amount_usd = fields.Monetary(
        related="contract_id.price_usd",
        string="Contract Amount (USD)",
        currency_field="currency_usd_id",
        store=True,
        readonly=True,
    )

    date = fields.Date(
        string="Plan Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )

    user_id = fields.Many2one(
        "res.users",
        string="Responsible Manager",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )

    deposit_mode = fields.Selection(
        [
            ("percent", "Percentage"),
            ("fixed", "Fixed Amount (USD)"),
        ],
        string="Deposit Type",
        required=True,
        default="percent",
    )

    deposit_value = fields.Float(
        string="Deposit Value",
        default=20.0,
        digits=(16, 2),
    )

    deposit_usd = fields.Monetary(
        string="Initial Deposit (USD)",
        compute="_compute_deposit_usd",
        store=True,
        currency_field="currency_usd_id",
    )

    installment_count = fields.Integer(
        string="Number of Installments",
        default=12,
        required=True,
    )

    schedule_interval = fields.Selection(
        [
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
        ],
        string="Payment Frequency",
        default="monthly",
        required=True,
    )

    first_payment_date = fields.Date(
        string="First Installment Date",
        required=True,
        # One month after the deposit, so deposit and first
        # installment do not fall on the same day by default.
        default=lambda self: fields.Date.context_today(self)
        + relativedelta(months=1),
    )

    schedule_currency_id = fields.Many2one(
        "res.currency",
        string="Schedule Currency",
        required=True,
        default=lambda self: self.env.ref("base.USD"),
    )

    schedule_exchange_rate = fields.Float(
        string="TJS per USD",
        digits=(12, 6),
        default=1.0,
        help="TJS for one USD. USD schedules use 1.",
    )

    schedule_ids = fields.One2many(
        "construction.payment.schedule",
        "plan_id",
        string="Payment Schedule",
    )

    scheduled_usd = fields.Monetary(
        string="Scheduled (USD)",
        compute="_compute_financials",
        store=True,
        currency_field="currency_usd_id",
    )

    paid_usd = fields.Monetary(
        string="Paid (USD)",
        compute="_compute_financials",
        store=True,
        currency_field="currency_usd_id",
    )

    balance_usd = fields.Monetary(
        string="Balance (USD)",
        compute="_compute_financials",
        store=True,
        currency_field="currency_usd_id",
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )

    notes = fields.Text(string="Notes")

    # Collections ("Должники")
    partner_phone = fields.Char(related="partner_id.phone", string="Телефон")
    overdue_usd = fields.Monetary(
        string="Просрочено (USD)", currency_field="currency_usd_id",
        compute="_compute_debt", store=True,
    )
    overdue_days = fields.Integer(
        string="Дней просрочки", compute="_compute_debt", store=True,
    )
    next_due_date = fields.Date(
        string="Следующий платёж", compute="_compute_debt", store=True,
    )
    overdue_0_30 = fields.Monetary(
        string="1–30 дн.", currency_field="currency_usd_id",
        compute="_compute_debt", store=True,
    )
    overdue_31_60 = fields.Monetary(
        string="31–60 дн.", currency_field="currency_usd_id",
        compute="_compute_debt", store=True,
    )
    overdue_61_90 = fields.Monetary(
        string="61–90 дн.", currency_field="currency_usd_id",
        compute="_compute_debt", store=True,
    )
    overdue_90 = fields.Monetary(
        string="Более 90 дн.", currency_field="currency_usd_id",
        compute="_compute_debt", store=True,
    )
    next_due_usd = fields.Monetary(
        string="Сумма следующего (USD)", currency_field="currency_usd_id",
        compute="_compute_debt", store=True,
    )

    @api.depends(
        "schedule_ids",
        "schedule_ids.state",
        "schedule_ids.balance_usd",
        "schedule_ids.due_date",
    )
    def _compute_debt(self):
        today = fields.Date.context_today(self)
        for plan in self:
            lines = plan.schedule_ids.filtered(lambda l: l.balance_usd > 0.01)
            overdue = lines.filtered(lambda l: l.due_date and l.due_date < today)
            upcoming = (lines - overdue).sorted("due_date")
            plan.overdue_usd = sum(overdue.mapped("balance_usd"))
            plan.overdue_days = (
                (today - min(overdue.mapped("due_date"))).days if overdue else 0
            )
            plan.next_due_date = upcoming[:1].due_date or False
            plan.next_due_usd = upcoming[:1].balance_usd or 0.0
            buckets = [0.0, 0.0, 0.0, 0.0]
            for line in overdue:
                days = (today - line.due_date).days
                index = 0 if days <= 30 else 1 if days <= 60 else 2 if days <= 90 else 3
                buckets[index] += line.balance_usd
            (plan.overdue_0_30, plan.overdue_31_60,
             plan.overdue_61_90, plan.overdue_90) = buckets

    def _terminate(self):
        """Close the plan when its contract is terminated (internal)."""
        for plan in self:
            if plan.state in ("confirmed", "closed", "draft"):
                super(ConstructionPaymentPlan, plan).write({"state": "cancelled"})
        return True

    def action_open_cash_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Принять платёж"),
            "res_model": "construction.cash.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_contract_id": self.contract_id.id,
            },
        }

    @api.depends("deposit_mode", "deposit_value", "contract_amount_usd")
    def _compute_deposit_usd(self):
        for plan in self:
            if plan.deposit_mode == "percent":
                plan.deposit_usd = (
                    plan.contract_amount_usd * plan.deposit_value / 100.0
                )
            else:
                plan.deposit_usd = plan.deposit_value

    @api.depends(
        "contract_amount_usd",
        "schedule_ids.amount_usd",
        "schedule_ids.paid_usd",
        "schedule_ids.payment_ids.state",
    )
    def _compute_financials(self):
        for plan in self:
            plan.scheduled_usd = sum(plan.schedule_ids.mapped("amount_usd"))
            plan.paid_usd = sum(plan.schedule_ids.mapped("paid_usd"))
            plan.balance_usd = max(
                plan.contract_amount_usd - plan.paid_usd, 0.0
            )

    @api.constrains("deposit_mode", "deposit_value", "contract_amount_usd")
    def _check_deposit(self):
        for plan in self:
            if plan.deposit_value < 0:
                raise ValidationError(_("Deposit value cannot be negative."))
            if plan.deposit_usd > plan.contract_amount_usd:
                raise ValidationError(
                    _("Initial deposit cannot exceed the contract amount.")
                )

    @api.constrains("installment_count")
    def _check_installment_count(self):
        for plan in self:
            if plan.installment_count < 1:
                raise ValidationError(
                    _("Number of installments must be at least 1.")
                )

    @api.constrains("schedule_exchange_rate", "schedule_currency_id")
    def _check_schedule_rate(self):
        usd = self.env.ref("base.USD")
        for plan in self:
            if (
                plan.schedule_currency_id
                and plan.schedule_currency_id != usd
                and plan.schedule_exchange_rate <= 0
            ):
                raise ValidationError(
                    _("A positive USD/TJS exchange rate is required.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            contract_id = vals.get("contract_id")
            contract = self.env["construction.contract"].browse(
                contract_id
            ).exists()

            if not contract or contract.state != "confirmed":
                raise UserError(
                    _("A payment plan can only be created for a confirmed contract.")
                )

            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code(
                        "construction.payment.plan"
                    )
                    or _("New")
                )

            if not vals.get("date"):
                vals["date"] = contract.contract_date

        return super().create(vals_list)

    def write(self, vals):
        for plan in self:
            if plan.state != "draft":
                raise UserError(
                    _("Only draft payment plans can be modified.")
                )
            if "state" in vals:
                raise UserError(
                    _("Use the payment plan action buttons to change status.")
                )
        return super().write(vals)

    def unlink(self):
        for plan in self:
            if plan.state != "draft":
                raise UserError(
                    _("Only draft payment plans can be deleted.")
                )
            if any(
                line.payment_ids
                for line in plan.schedule_ids
            ):
                raise UserError(
                    _("A payment plan with payments cannot be deleted.")
                )
        return super().unlink()

    def action_generate_schedule(self):
        usd = self.env.ref("base.USD")

        for plan in self:
            if plan.state != "draft":
                raise UserError(
                    _("Schedule can only be generated for draft plans.")
                )

            if plan.schedule_ids:
                raise UserError(
                    _("A schedule already exists. Delete its lines manually before generating a new one.")
                )

            if plan.installment_count < 1:
                raise ValidationError(
                    _("Number of installments must be at least 1.")
                )

            if not plan.first_payment_date:
                raise ValidationError(
                    _("Please specify the first installment date.")
                )

            currency = plan.schedule_currency_id
            if not currency:
                raise ValidationError(
                    _("Please select a schedule currency.")
                )

            rate = 1.0
            if currency != usd:
                rate = plan.schedule_exchange_rate
                if rate <= 0:
                    raise ValidationError(
                        _("A positive USD/TJS exchange rate is required.")
                    )

            contract_usd = plan.contract_amount_usd
            deposit_usd = plan.deposit_usd
            remaining_usd = contract_usd - deposit_usd

            if contract_usd <= 0:
                raise ValidationError(
                    _("Contract amount must be greater than zero.")
                )

            if deposit_usd < 0 or deposit_usd > contract_usd:
                raise ValidationError(
                    _("Invalid initial deposit amount.")
                )

            if remaining_usd <= 0:
                raise ValidationError(
                    _("The contract must have a balance for installments.")
                )

            def to_schedule_currency(amount_usd):
                return currency.round(amount_usd * rate)

            total_schedule_amount = to_schedule_currency(contract_usd)
            deposit_amount = to_schedule_currency(deposit_usd)
            installment_usd = remaining_usd / plan.installment_count

            lines = []

            if deposit_amount > 0:
                lines.append({
                    "name": _("Initial Deposit"),
                    "plan_id": plan.id,
                    "due_date": plan.date,
                    "amount": deposit_amount,
                    "currency_id": currency.id,
                    "exchange_rate": rate,
                })

            created_installments_amount = 0.0

            for index in range(plan.installment_count):
                if index == plan.installment_count - 1:
                    amount = currency.round(
                        total_schedule_amount
                        - deposit_amount
                        - created_installments_amount
                    )
                else:
                    amount = to_schedule_currency(installment_usd)
                    created_installments_amount += amount

                if amount <= 0:
                    raise ValidationError(
                        _("Generated installment amount must be positive.")
                    )

                months = (
                    index
                    if plan.schedule_interval == "monthly"
                    else index * 3
                )
                due_date = plan.first_payment_date + relativedelta(
                    months=months
                )

                lines.append({
                    "name": _("Installment %s") % (index + 1),
                    "plan_id": plan.id,
                    "due_date": due_date,
                    "amount": amount,
                    "currency_id": currency.id,
                    "exchange_rate": rate,
                })

            self.env["construction.payment.schedule"].create(lines)

        return True

    def action_confirm(self):
        for plan in self:
            if plan.state != "draft":
                raise UserError(
                    _("Only draft payment plans can be confirmed.")
                )

            if not plan.schedule_ids:
                raise UserError(
                    _("Generate or add payment schedule lines before confirmation.")
                )

            if any(line.amount <= 0 for line in plan.schedule_ids):
                raise ValidationError(
                    _("All schedule amounts must be positive.")
                )

            scheduled = sum(plan.schedule_ids.mapped("amount_usd"))
            if abs(scheduled - plan.contract_amount_usd) > 0.01:
                raise ValidationError(
                    _(
                        "The payment schedule total (%s USD) must equal "
                        "the contract amount (%s USD)."
                    )
                    % (scheduled, plan.contract_amount_usd)
                )

            super(ConstructionPaymentPlan, plan).write({
                "state": "confirmed"
            })

        return True

    def action_cancel(self):
        for plan in self:
            if plan.state != "draft":
                raise UserError(
                    _("Only draft payment plans can be cancelled.")
                )

            if any(
                payment.state == "posted"
                for payment in plan.schedule_ids.mapped("payment_ids")
            ):
                raise UserError(
                    _("A plan with posted payments cannot be cancelled.")
                )

            super(ConstructionPaymentPlan, plan).write({
                "state": "cancelled"
            })

        return True

    def _close_if_paid(self):
        for plan in self:
            plan.invalidate_recordset()
            if (
                plan.state == "confirmed"
                and plan.balance_usd <= 0.01
            ):
                super(ConstructionPaymentPlan, plan).write({
                    "state": "closed"
                })
        return True
