from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConstructionPayment(models.Model):
    _name = "construction.payment"
    _description = "Construction Payment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "payment_date desc, id desc"

    name = fields.Char(
        required=True, copy=False, readonly=True,
        default=lambda self: _("New"), tracking=True
    )
    plan_id = fields.Many2one(related="schedule_id.plan_id", store=True, readonly=True)
    schedule_id = fields.Many2one(
        "construction.payment.schedule", required=True,
        ondelete="restrict", index=True, tracking=True
    )
    contract_id = fields.Many2one(
        related="schedule_id.plan_id.contract_id", store=True, readonly=True
    )
    partner_id = fields.Many2one(
        related="schedule_id.plan_id.partner_id", store=True, readonly=True
    )

    project_id = fields.Many2one(
        related="schedule_id.plan_id.project_id",
        string="Project",
        store=True,
        readonly=True,
        index=True,
    )
    payment_date = fields.Date(
        required=True, default=fields.Date.context_today, tracking=True
    )
    amount = fields.Monetary(required=True, tracking=True)
    currency_id = fields.Many2one(
        "res.currency", required=True,
        default=lambda self: self.env.ref("base.USD")
    )
    exchange_rate = fields.Float(
        string="TJS per USD", digits=(12, 6), default=1.0,
        help="Rate on the payment date. For USD payments use 1."
    )
    currency_usd_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.ref("base.USD"),
        readonly=True
    )
    amount_usd = fields.Monetary(
        compute="_compute_amount_usd", store=True,
        currency_field="currency_usd_id"
    )
    method_id = fields.Many2one(
        "construction.payment.method", required=True, ondelete="restrict"
    )
    reference = fields.Char(string="Receipt / Bank Reference")
    user_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user
    )
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, index=True
    )
    notes = fields.Text()

    @api.depends("amount", "currency_id", "exchange_rate")
    def _compute_amount_usd(self):
        usd = self.env.ref("base.USD")
        for payment in self:
            if payment.currency_id == usd:
                payment.amount_usd = payment.amount
            elif payment.exchange_rate > 0:
                payment.amount_usd = payment.amount / payment.exchange_rate
            else:
                payment.amount_usd = 0

    @api.constrains("amount", "exchange_rate", "currency_id")
    def _check_amount(self):
        for payment in self:
            if payment.amount <= 0:
                raise ValidationError(_("Payment amount must be positive."))
            if payment.currency_id != self.env.ref("base.USD") and payment.exchange_rate <= 0:
                raise ValidationError(_("A positive USD/TJS rate is required."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise UserError(_("Payments must be created in Draft state."))
            schedule = self.env["construction.payment.schedule"].browse(
                vals.get("schedule_id")
            ).exists()
            if not schedule or schedule.plan_id.state != "confirmed":
                raise UserError(_("Payments can only be created for confirmed plans."))
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "construction.payment"
                ) or _("New")
        return super().create(vals_list)

    def write(self, vals):
        for payment in self:
            if payment.state != "draft":
                raise UserError(_("Posted or cancelled payments cannot be edited."))
            if "state" in vals:
                raise UserError(_("Use payment action buttons to change status."))
        return super().write(vals)

    def unlink(self):
        for payment in self:
            if payment.state != "draft":
                raise UserError(_("Only draft payments can be deleted."))
        return super().unlink()

    def action_post(self):
        for payment in self:
            # Lock payment row to prevent posting the same payment twice concurrently.
            self.env.cr.execute(
                "SELECT id FROM construction_payment WHERE id = %s FOR UPDATE",
                [payment.id]
            )
            payment.invalidate_recordset()
            if payment.state != "draft":
                raise UserError(_("Only draft payments can be posted."))

            schedule = payment.schedule_id
            plan = schedule.plan_id

            # Lock schedule row to serialize payments against the same installment.
            self.env.cr.execute(
                "SELECT id FROM construction_payment_schedule WHERE id = %s FOR UPDATE",
                [schedule.id]
            )
            schedule.invalidate_recordset()
            plan.invalidate_recordset()

            if plan.state != "confirmed":
                raise UserError(_("The financial plan must be confirmed first."))

            if payment.amount_usd > schedule.balance_usd + 0.01:
                raise UserError(_("Payment exceeds the remaining scheduled amount."))

            super(ConstructionPayment, payment).write({"state": "posted"})
            plan._close_if_paid()

        return True

    def action_cancel(self):
        for payment in self:
            if payment.state != "draft":
                raise UserError(_("Only draft payments can be cancelled."))
            super(ConstructionPayment, payment).write({"state": "cancelled"})
        return True
