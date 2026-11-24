from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionCashWizard(models.TransientModel):
    """Cash desk: receive money from a client.

    The amount is spread over the unpaid schedule lines of the contract,
    oldest first; one posted payment is created per line.
    """

    _name = "construction.cash.wizard"
    _description = "Принять платёж"

    partner_id = fields.Many2one("res.partner", string="Клиент", required=True)
    contract_id = fields.Many2one(
        "construction.contract", string="Договор", required=True,
        domain="[('partner_id', '=', partner_id), ('state', '=', 'confirmed')]",
    )
    plan_id = fields.Many2one(
        "construction.payment.plan", string="План оплаты", compute="_compute_plan",
    )
    currency_usd_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.ref("base.USD"),
    )
    balance_usd = fields.Monetary(
        related="plan_id.balance_usd", string="Остаток долга (USD)",
        currency_field="currency_usd_id",
    )
    overdue_usd = fields.Monetary(
        related="plan_id.overdue_usd", string="Просрочено (USD)",
        currency_field="currency_usd_id",
    )
    next_due_date = fields.Date(related="plan_id.next_due_date")

    payment_date = fields.Date(
        string="Дата", required=True, default=fields.Date.context_today,
    )
    pay_currency = fields.Selection(
        [("usd", "USD"), ("tjs", "Сомони")], string="Валюта",
        default="usd", required=True,
    )
    amount = fields.Float(string="Сумма", digits=(16, 2))
    # Currency the amount is currently expressed in (to convert only on a
    # real switch USD <-> TJS, not on every onchange round-trip).
    amount_currency = fields.Selection(
        [("usd", "USD"), ("tjs", "Сомони")], default="usd",
    )
    exchange_rate = fields.Float(string="Курс USD/TJS", digits=(12, 6))
    amount_usd = fields.Monetary(
        string="В долларах", currency_field="currency_usd_id",
        compute="_compute_amount_usd",
    )
    method_id = fields.Many2one(
        "construction.payment.method", string="Способ оплаты", required=True,
        default=lambda self: self.env["construction.payment.method"].search([], limit=1),
    )
    receipt_number = fields.Char(
        string="№ квитанции", help="Номер квитанции вручную (как в прежней системе). "
                                   "Пусто — номер присвоится автоматически.")
    reference = fields.Char(string="№ документа банка")
    allocation_preview = fields.Html(
        string="Распределение", compute="_compute_allocation", sanitize=False,
    )

    # ------------------------------------------------------------------

    @api.onchange("partner_id")
    def _onchange_partner(self):
        if self.contract_id.partner_id != self.partner_id:
            contracts = self.env["construction.contract"].search([
                ("partner_id", "=", self.partner_id.id),
                ("state", "=", "confirmed"),
            ])
            self.contract_id = contracts[:1] if len(contracts) == 1 else False

    @api.depends("contract_id")
    def _compute_plan(self):
        Plan = self.env["construction.payment.plan"]
        for wiz in self:
            wiz.plan_id = Plan.search([
                ("contract_id", "=", wiz.contract_id.id),
                ("state", "=", "confirmed"),
            ], limit=1) if wiz.contract_id else False

    @api.onchange("contract_id")
    def _onchange_contract(self):
        plan = self.plan_id
        if not plan:
            return
        # Suggest: everything overdue, otherwise the next installment.
        self.exchange_rate = self.exchange_rate or plan.project_id.usd_tjs_rate or 0.0
        suggested = plan.overdue_usd or plan.next_due_usd
        if self.pay_currency == "tjs" and self.exchange_rate:
            suggested = round(suggested * self.exchange_rate, 2)
        self.amount = suggested
        self.amount_currency = self.pay_currency

    @api.onchange("pay_currency")
    def _onchange_currency(self):
        if self.pay_currency == self.amount_currency:
            return
        rate = self.exchange_rate or self.plan_id.project_id.usd_tjs_rate
        if rate and self.amount:
            if self.pay_currency == "tjs":
                self.amount = round(self.amount * rate, 2)
            else:
                self.amount = round(self.amount / rate, 2)
        if rate and not self.exchange_rate:
            self.exchange_rate = rate
        self.amount_currency = self.pay_currency

    @api.depends("amount", "pay_currency", "exchange_rate")
    def _compute_amount_usd(self):
        for wiz in self:
            if wiz.pay_currency == "usd":
                wiz.amount_usd = wiz.amount
            else:
                wiz.amount_usd = (
                    wiz.amount / wiz.exchange_rate if wiz.exchange_rate > 0 else 0.0
                )

    def _allocation(self):
        """[(schedule_line, amount_usd)] oldest unpaid first."""
        self.ensure_one()
        rest = self.amount_usd
        result = []
        lines = self.plan_id.schedule_ids.filtered(
            lambda l: l.balance_usd > 0.01
        ).sorted(lambda l: (l.due_date, l.id))
        for line in lines:
            if rest <= 0.005:
                break
            take = min(line.balance_usd, rest)
            result.append((line, take))
            rest -= take
        return result, rest

    @api.depends("amount_usd", "plan_id")
    def _compute_allocation(self):
        for wiz in self:
            if not wiz.plan_id or wiz.amount_usd <= 0:
                wiz.allocation_preview = False
                continue
            alloc, rest = wiz._allocation()
            fmt = lambda v: "{:,.2f}".format(v).replace(",", " ")
            rows = Markup("").join(
                Markup(
                    "<tr><td>%s</td><td>%s</td><td class='text-end'>$ %s</td>"
                    "<td class='text-end'><b>$ %s</b></td><td>%s</td></tr>"
                ) % (
                    escape(line.name),
                    line.due_date.strftime("%d.%m.%Y"),
                    fmt(line.balance_usd),
                    fmt(take),
                    _("закрыт") if take >= line.balance_usd - 0.01 else _("частично"),
                )
                for line, take in alloc
            )
            warn = Markup("")
            if rest > 0.01:
                warn = Markup(
                    "<div class='alert alert-danger mt-2'>%s</div>"
                ) % (_("Сумма больше долга на $ %s") % fmt(rest))
            wiz.allocation_preview = Markup(
                "<table class='table table-sm'><thead><tr><th>Платёж</th>"
                "<th>Срок</th><th class='text-end'>Долг</th>"
                "<th class='text-end'>Оплата</th><th></th></tr></thead>"
                "<tbody>%s</tbody></table>%s"
            ) % (rows, warn)

    # ------------------------------------------------------------------

    def action_receive(self):
        self.ensure_one()
        if not self.plan_id:
            raise UserError(_("У договора нет подтверждённого плана оплаты."))
        if self.amount <= 0:
            raise ValidationError(_("Введите сумму больше нуля."))
        if self.pay_currency == "tjs" and self.exchange_rate <= 0:
            raise ValidationError(_("Укажите курс USD/TJS."))
        alloc, rest = self._allocation()
        if rest > 0.01:
            raise ValidationError(_(
                "Сумма больше остатка долга (%(debt)s USD).",
                debt="{:,.2f}".format(self.plan_id.balance_usd).replace(",", " "),
            ))

        number = (self.receipt_number or "").strip()
        Receipt = self.env["construction.cash.receipt"]
        if number:
            Receipt._check_number_free(number)

        Payment = self.env["construction.payment"]
        usd = self.env.ref("base.USD")
        tjs = self.env.ref("base.TJS")
        if not tjs.active:
            tjs.sudo().active = True
        receipt = Receipt.create({
            "name": number or "/",
            "date": self.payment_date,
            "partner_id": self.plan_id.partner_id.id,
            "contract_id": self.plan_id.contract_id.id,
            "method_id": self.method_id.id,
            "pay_currency": self.pay_currency,
            "amount": self.amount,
            "exchange_rate": self.exchange_rate if self.pay_currency == "tjs" else (
                self.plan_id.project_id.usd_tjs_rate or 0.0),
            "attachment": self.reference or False,
        })
        payments = Payment
        for line, take in alloc:
            if self.pay_currency == "usd":
                vals = {"amount": round(take, 2), "currency_id": usd.id,
                        "exchange_rate": 1.0}
            else:
                vals = {"amount": round(take * self.exchange_rate, 2),
                        "currency_id": tjs.id,
                        "exchange_rate": self.exchange_rate}
            vals.update({
                "schedule_id": line.id,
                "payment_date": self.payment_date,
                "method_id": self.method_id.id,
                "reference": self.reference,
                "user_id": self.env.uid,
                "receipt_id": receipt.id,
            })
            payments |= Payment.create(vals)
        payments.action_post()

        receipt._compute_basis()

        return {
            "type": "ir.actions.act_window",
            "name": _("Приходный ордер"),
            "res_model": "construction.cash.receipt",
            "view_mode": "form",
            "res_id": receipt.id,
            "target": "current",
        }
