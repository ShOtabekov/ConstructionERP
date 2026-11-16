from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConstructionPaymentSchedule(models.Model):
    _name = "construction.payment.schedule"
    _description = "Construction Payment Schedule"
    _order = "due_date, id"

    name = fields.Char(required=True)
    plan_id = fields.Many2one(
        "construction.payment.plan", required=True,
        ondelete="cascade", index=True
    )

    partner_id = fields.Many2one(
        related="plan_id.partner_id",
        string="Buyer",
        store=True,
        readonly=True,
        index=True,
    )
    project_id = fields.Many2one(
        related="plan_id.project_id",
        string="Project",
        store=True,
        readonly=True,
        index=True,
    )
    due_date = fields.Date(required=True, index=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(
        "res.currency", required=True,
        default=lambda self: self.env.ref("base.USD")
    )
    exchange_rate = fields.Float(
        string="TJS per USD", digits=(12, 6), default=1.0,
        help="For TJS schedules, enter TJS for one USD. USD schedules use 1."
    )
    currency_usd_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.ref("base.USD"),
        readonly=True
    )
    amount_usd = fields.Monetary(
        compute="_compute_amount_usd", store=True,
        currency_field="currency_usd_id"
    )
    payment_ids = fields.One2many(
        "construction.payment", "schedule_id", string="Payments"
    )
    paid_usd = fields.Monetary(
        compute="_compute_paid", store=True, currency_field="currency_usd_id"
    )
    balance_usd = fields.Monetary(
        compute="_compute_paid", store=True, currency_field="currency_usd_id"
    )
    state = fields.Selection(
        [("pending", "Pending"), ("partial", "Partially Paid"),
         ("paid", "Paid"), ("overdue", "Overdue")],
        compute="_compute_paid", store=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            plan = self.env["construction.payment.plan"].browse(
                vals.get("plan_id")
            ).exists()
            if not plan or plan.state != "draft":
                raise UserError(_("Schedule lines can only be added to draft plans."))
        return super().create(vals_list)

    @api.depends("amount", "currency_id", "exchange_rate")
    def _compute_amount_usd(self):
        usd = self.env.ref("base.USD")
        for line in self:
            if line.currency_id == usd:
                line.amount_usd = line.amount
            elif line.exchange_rate > 0:
                line.amount_usd = line.amount / line.exchange_rate
            else:
                line.amount_usd = 0

    @api.depends(
        "amount_usd",
        "payment_ids.amount_usd",
        "payment_ids.state",
        "due_date",
    )
    def _compute_paid(self):
        today = fields.Date.context_today(self)

        for line in self:
            line.paid_usd = sum(
                payment.amount_usd
                for payment in line.payment_ids
                if payment.state == "posted"
            )

            line.balance_usd = max(
                line.amount_usd - line.paid_usd, 0.0
            )

            if line.balance_usd <= 0.01:
                line.state = "paid"
            elif line.due_date < today:
                line.state = "overdue"
            elif line.paid_usd > 0:
                line.state = "partial"
            else:
                line.state = "pending"

    @api.constrains("amount", "exchange_rate", "currency_id")
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_("Scheduled amount must be positive."))
            if line.currency_id != self.env.ref("base.USD") and line.exchange_rate <= 0:
                raise ValidationError(_("A positive USD/TJS rate is required."))

    def write(self, vals):
        for line in self:
            if line.plan_id.state != "draft":
                raise UserError(_("Confirmed schedules cannot be modified."))
        return super().write(vals)

    def unlink(self):
        for line in self:
            if line.plan_id.state != "draft" or line.payment_ids:
                raise UserError(_("This schedule line cannot be deleted."))
        return super().unlink()

    @api.model
    def _cron_update_overdue(self):
        """Daily: move unpaid lines past their due date to Overdue.

        "state" is a stored compute that otherwise changes only when a
        payment is posted, so it would never become Overdue by itself.
        """
        today = fields.Date.context_today(self)
        lines = self.sudo().search([
            ("state", "in", ("pending", "partial")),
            ("due_date", "<", today),
        ])
        if lines:
            lines.modified(["due_date"])
            self.env.flush_all()
        return True
