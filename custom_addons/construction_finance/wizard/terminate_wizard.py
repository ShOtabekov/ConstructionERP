from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..models.project import PENALTY_MODES


class ConstructionTerminateWizard(models.TransientModel):
    _name = "construction.terminate.wizard"
    _description = "Расторжение договора"

    contract_id = fields.Many2one(
        "construction.contract", string="Договор", required=True,
        domain="[('state', '=', 'confirmed')]",
    )
    partner_id = fields.Many2one(related="contract_id.partner_id", string="Клиент")
    apartment_id = fields.Many2one(related="contract_id.apartment_id", string="Помещение")
    plan_id = fields.Many2one(
        "construction.payment.plan", compute="_compute_amounts", string="План оплаты",
    )
    currency_usd_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.ref("base.USD"),
    )
    contract_price_usd = fields.Monetary(
        related="contract_id.price_usd", string="Цена договора",
        currency_field="currency_usd_id",
    )
    paid_usd = fields.Monetary(
        string="Внесено клиентом", currency_field="currency_usd_id",
        compute="_compute_amounts",
    )
    date = fields.Date(
        string="Дата расторжения", required=True, default=fields.Date.context_today,
    )
    reason = fields.Text(string="Причина")

    penalty_mode = fields.Selection(PENALTY_MODES, string="Штраф", required=True,
                                    default="paid_percent")
    penalty_value = fields.Float(string="Размер штрафа", digits=(16, 2))
    penalty_usd = fields.Monetary(
        string="Удерживаем", currency_field="currency_usd_id",
        compute="_compute_amounts",
    )
    refund_usd = fields.Monetary(
        string="Вернуть клиенту", currency_field="currency_usd_id",
        compute="_compute_amounts",
    )

    refund_mode = fields.Selection(
        [("lump", "Одной суммой"), ("schedule", "По графику")],
        string="Как возвращаем", default="lump", required=True,
    )
    refund_count = fields.Integer(string="Количество выплат", default=6)
    refund_interval = fields.Selection(
        [("monthly", "Ежемесячно"), ("quarterly", "Ежеквартально")],
        string="Периодичность", default="monthly", required=True,
    )
    refund_first_date = fields.Date(
        string="Первая выплата", default=fields.Date.context_today,
    )
    refund_preview = fields.Html(compute="_compute_preview", sanitize=False)

    @api.onchange("contract_id")
    def _onchange_contract(self):
        project = self.contract_id.project_id
        if project:
            self.penalty_mode = project.termination_penalty_mode
            self.penalty_value = project.termination_penalty_value

    @api.depends("contract_id", "penalty_mode", "penalty_value")
    def _compute_amounts(self):
        Plan = self.env["construction.payment.plan"].sudo()
        for wiz in self:
            plan = Plan.search([
                ("contract_id", "=", wiz.contract_id.id),
                ("state", "in", ("confirmed", "closed")),
            ], limit=1) if wiz.contract_id else Plan
            wiz.plan_id = plan
            paid = plan.paid_usd if plan else 0.0
            wiz.paid_usd = paid
            if wiz.penalty_mode == "paid_percent":
                penalty = paid * wiz.penalty_value / 100.0
            elif wiz.penalty_mode == "price_percent":
                penalty = wiz.contract_id.price_usd * wiz.penalty_value / 100.0
            elif wiz.penalty_mode == "fixed":
                penalty = wiz.penalty_value
            else:
                penalty = 0.0
            penalty = round(min(max(penalty, 0.0), paid), 2)
            wiz.penalty_usd = penalty
            wiz.refund_usd = round(paid - penalty, 2)

    def _refund_lines(self):
        self.ensure_one()
        total = self.refund_usd
        if total <= 0:
            return []
        if self.refund_mode == "lump":
            return [(self.refund_first_date or self.date, total)]
        count = max(self.refund_count, 1)
        step = 1 if self.refund_interval == "monthly" else 3
        part = round(total / count, 2)
        lines = []
        for index in range(count):
            amount = part if index < count - 1 else round(total - part * (count - 1), 2)
            date = (self.refund_first_date or self.date) + relativedelta(months=index * step)
            lines.append((date, amount))
        return lines

    @api.depends("refund_usd", "refund_mode", "refund_count", "refund_interval",
                 "refund_first_date", "date")
    def _compute_preview(self):
        fmt = lambda v: "{:,.2f}".format(v).replace(",", " ")
        for wiz in self:
            lines = wiz._refund_lines()
            if not lines:
                wiz.refund_preview = False
                continue
            rows = Markup("").join(
                Markup("<tr><td>%s</td><td>%s</td><td class='text-end'>$ %s</td></tr>")
                % (i, d.strftime("%d.%m.%Y"), fmt(a))
                for i, (d, a) in enumerate(lines, 1)
            )
            wiz.refund_preview = Markup(
                "<table class='table table-sm'><thead><tr><th>№</th><th>Дата</th>"
                "<th class='text-end'>Сумма</th></tr></thead><tbody>%s</tbody></table>"
            ) % rows

    def action_terminate(self):
        self.ensure_one()
        contract = self.contract_id
        if contract.state != "confirmed":
            raise UserError(_("Договор уже не действует."))
        if self.penalty_value < 0:
            raise ValidationError(_("Штраф не может быть отрицательным."))
        if self.penalty_mode in ("paid_percent", "price_percent") and self.penalty_value > 100:
            raise ValidationError(_("Процент штрафа не может быть больше 100."))
        if self.refund_mode == "schedule" and self.refund_count < 1:
            raise ValidationError(_("Количество выплат должно быть не меньше 1."))

        plan = self.plan_id
        refund = self.env["construction.refund"].create({
            "contract_id": contract.id,
            "plan_id": plan.id or False,
            "date": self.date,
            "reason": self.reason,
            "contract_price_usd": contract.price_usd,
            "paid_usd": self.paid_usd,
            "penalty_mode": self.penalty_mode,
            "penalty_value": self.penalty_value,
            "penalty_usd": self.penalty_usd,
            "refund_usd": self.refund_usd,
            "refund_mode": self.refund_mode,
            "line_ids": [
                (0, 0, {"due_date": date, "amount_usd": amount})
                for date, amount in self._refund_lines()
            ],
        })
        plan._terminate()
        contract._cancel_for_termination()
        contract.message_post(body=_(
            "Договор расторгнут (%(ref)s). Внесено $ %(paid)s, штраф $ %(pen)s, "
            "к возврату $ %(ret)s.",
            ref=refund.name, paid=self.paid_usd, pen=self.penalty_usd, ret=self.refund_usd,
        ))
        return {
            "type": "ir.actions.act_window",
            "name": refund.name,
            "res_model": "construction.refund",
            "res_id": refund.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
