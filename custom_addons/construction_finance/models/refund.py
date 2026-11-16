from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .project import PENALTY_MODES


class ConstructionRefund(models.Model):
    """Contract termination and money returned to the client."""

    _name = "construction.refund"
    _description = "Расторжение и возврат"
    _inherit = ["mail.thread"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Номер", required=True, readonly=True, copy=False,
        default=lambda self: _("New"),
    )
    contract_id = fields.Many2one(
        "construction.contract", string="Договор", required=True,
        readonly=True, ondelete="restrict", index=True,
    )
    partner_id = fields.Many2one(related="contract_id.partner_id", store=True, string="Клиент")
    partner_phone = fields.Char(related="partner_id.phone", string="Телефон")
    apartment_id = fields.Many2one(related="contract_id.apartment_id", store=True, string="Помещение")
    project_id = fields.Many2one(related="contract_id.project_id", store=True, string="Проект")
    plan_id = fields.Many2one("construction.payment.plan", string="План оплаты", readonly=True)
    date = fields.Date(string="Дата расторжения", required=True, readonly=True)
    reason = fields.Text(string="Причина")
    user_id = fields.Many2one(
        "res.users", string="Оформил", default=lambda self: self.env.user, readonly=True,
    )

    currency_usd_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.ref("base.USD"), readonly=True,
    )
    contract_price_usd = fields.Monetary(
        string="Цена договора", currency_field="currency_usd_id", readonly=True,
    )
    paid_usd = fields.Monetary(
        string="Внесено клиентом", currency_field="currency_usd_id", readonly=True,
    )
    penalty_mode = fields.Selection(PENALTY_MODES, string="Штраф", readonly=True)
    penalty_value = fields.Float(string="Размер штрафа", readonly=True)
    penalty_usd = fields.Monetary(
        string="Удержано (штраф)", currency_field="currency_usd_id", readonly=True,
    )
    refund_usd = fields.Monetary(
        string="К возврату", currency_field="currency_usd_id", readonly=True,
    )
    refund_mode = fields.Selection(
        [("lump", "Одной суммой"), ("schedule", "По графику")],
        string="Возврат", readonly=True,
    )
    line_ids = fields.One2many("construction.refund.line", "refund_id", string="Выплаты")
    refunded_usd = fields.Monetary(
        string="Выплачено", currency_field="currency_usd_id",
        compute="_compute_refunded", store=True,
    )
    remaining_usd = fields.Monetary(
        string="Осталось выплатить", currency_field="currency_usd_id",
        compute="_compute_refunded", store=True,
    )
    state = fields.Selection(
        [("open", "Выплачивается"), ("done", "Выплачено")],
        string="Статус", compute="_compute_refunded", store=True, tracking=True,
    )

    @api.depends("refund_usd", "line_ids.paid", "line_ids.amount_usd")
    def _compute_refunded(self):
        for refund in self:
            paid = sum(refund.line_ids.filtered("paid").mapped("amount_usd"))
            refund.refunded_usd = paid
            refund.remaining_usd = max(refund.refund_usd - paid, 0.0)
            refund.state = "done" if refund.remaining_usd <= 0.01 else "open"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "construction.refund"
                ) or _("New")
        return super().create(vals_list)

    def unlink(self):
        raise UserError(_("Документ расторжения удалить нельзя."))


class ConstructionRefundLine(models.Model):
    _name = "construction.refund.line"
    _description = "Выплата возврата"
    _order = "due_date, id"

    refund_id = fields.Many2one(
        "construction.refund", required=True, ondelete="cascade", index=True,
    )
    partner_id = fields.Many2one(related="refund_id.partner_id", store=True, string="Клиент")
    currency_usd_id = fields.Many2one(related="refund_id.currency_usd_id")
    due_date = fields.Date(string="Срок", required=True)
    amount_usd = fields.Monetary(
        string="Сумма (USD)", currency_field="currency_usd_id", required=True,
    )
    paid = fields.Boolean(string="Выдано", readonly=True)
    paid_date = fields.Date(string="Дата выдачи")
    method_id = fields.Many2one("construction.payment.method", string="Способ")
    reference = fields.Char(string="№ документа")

    def action_mark_paid(self):
        for line in self:
            if line.paid:
                continue
            if not line.method_id:
                raise UserError(_("Укажите способ выдачи денег."))
            line.write({
                "paid": True,
                "paid_date": line.paid_date or fields.Date.context_today(self),
            })
            line.refund_id.message_post(body=_(
                "Выдано клиенту: $ %(amount)s (%(method)s)",
                amount="{:,.2f}".format(line.amount_usd).replace(",", " "),
                method=line.method_id.name,
            ))
        return True

    def action_unmark_paid(self):
        self.write({"paid": False})
        return True
