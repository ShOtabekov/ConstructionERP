"""Кассовые документы: приходный ордер (на каждый приём денег) и расход кассы."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..tools import tj_amount_words
from .print_docs import money, ru_date, tj_date

CURRENCIES = [("tjs", "Сомони"), ("usd", "USD")]

EXPENSE_CATEGORIES = [
    ("salary", "Зарплата"),
    ("materials", "Стройматериалы"),
    ("services", "Работы и услуги"),
    ("transport", "Транспорт"),
    ("household", "Хозяйственные расходы"),
    ("taxes", "Налоги и сборы"),
    ("refund", "Возврат клиенту"),
    ("bank", "Сдача в банк"),
    ("other", "Прочее"),
]


class CashDocMixin(models.AbstractModel):
    _name = "construction.cash.doc.mixin"
    _description = "Кассовый документ"

    currency_usd_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.ref("base.USD"), readonly=True)
    pay_currency = fields.Selection(CURRENCIES, string="Валюта", required=True, default="tjs")
    amount = fields.Float(string="Сумма", digits=(16, 2), required=True)
    exchange_rate = fields.Float(string="Курс USD/TJS", digits=(12, 4))
    amount_usd = fields.Monetary(
        string="Сумма (USD)", currency_field="currency_usd_id",
        compute="_compute_amount_usd", store=True)
    amount_tjs = fields.Float(string="Сумма (сомони)", digits=(16, 2),
                              compute="_compute_amount_usd", store=True)

    @api.depends("amount", "pay_currency", "exchange_rate")
    def _compute_amount_usd(self):
        for doc in self:
            rate = doc.exchange_rate or 0.0
            if doc.pay_currency == "usd":
                doc.amount_usd = doc.amount
                doc.amount_tjs = doc.amount * rate if rate else 0.0
            else:
                doc.amount_tjs = doc.amount
                doc.amount_usd = doc.amount / rate if rate else 0.0

    # --- печать ---------------------------------------------------------
    def _cur_label(self, lang="tj"):
        if self.pay_currency == "usd":
            return "доллари ИМА" if lang == "tj" else "долларов США"
        return "сомонӣ" if lang == "tj" else "сомони"

    def _words(self, lang="tj"):
        cur = "USD" if self.pay_currency == "usd" else "TJS"
        if lang == "tj":
            return tj_amount_words(self.amount, cur)
        return self.env["construction.contract"]._amount_words(self.amount, cur)

    def _money(self, v):
        return money(v)

    def _tj_date(self, d):
        return tj_date(d)

    def _ru_date(self, d):
        return ru_date(d)


class ConstructionCashReceipt(models.Model):
    _name = "construction.cash.receipt"
    _inherit = ["construction.cash.doc.mixin", "mail.thread"]
    _description = "Приходный кассовый ордер"
    _order = "date desc, id desc"

    name = fields.Char(string="№ квитанции", copy=False, default="/", tracking=True)
    date = fields.Date(string="Дата", required=True, default=fields.Date.context_today)
    partner_id = fields.Many2one("res.partner", string="Принято от", required=True)
    contract_id = fields.Many2one("construction.contract", string="Договор")
    apartment_id = fields.Many2one(related="contract_id.apartment_id", store=True, string="Помещение")
    project_id = fields.Many2one(related="contract_id.project_id", store=True, string="Проект")
    method_id = fields.Many2one("construction.payment.method", string="Способ")
    basis = fields.Char(string="Основание")
    attachment = fields.Char(string="Приложение")
    user_id = fields.Many2one("res.users", string="Кассир", default=lambda self: self.env.user)
    payment_ids = fields.One2many("construction.payment", "receipt_id", string="Платежи")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.cash.receipt") or "/"
        return super().create(vals_list)

    @api.model
    def _check_number_free(self, number, exclude=None):
        domain = [("name", "=", number)]
        if exclude:
            domain.append(("id", "not in", exclude.ids))
        if self.sudo().search_count(domain, limit=1):
            raise ValidationError(_("Квитанция с номером %s уже есть.") % number)

    @api.constrains("name")
    def _check_unique_name(self):
        for rec in self:
            if rec.name and rec.name != "/":
                self._check_number_free(rec.name, exclude=rec)

    def _compute_basis(self):
        """«Пардохти ҳисса моҳи 10 Д-05-07 (94)» по разнесённым платежам."""
        for rec in self:
            contract = rec.contract_id
            if not contract:
                continue
            labels = []
            for pay in rec.payment_ids.sorted(lambda p: (p.schedule_id.due_date, p.id)):
                idx = pay.schedule_id._print_index()
                labels.append("пардохти аввала" if idx == 0 else str(idx))
            nums = [l for l in labels if l.isdigit()]
            parts = []
            if "пардохти аввала" in labels:
                parts.append("Пардохти аввала")
            if nums:
                rng = nums[0] if len(nums) == 1 else "%s-%s" % (nums[0], nums[-1])
                parts.append(("пардохти ҳисса моҳи %s" if parts else "Пардохти ҳисса моҳи %s") % rng)
            rec.basis = "%s %s (%s)" % (", ".join(parts) or "Пардохти ҳисса",
                                        contract.apartment_id.unit_code or "",
                                        contract.number_print)


class ConstructionPaymentReceiptLink(models.Model):
    _inherit = "construction.payment"

    receipt_id = fields.Many2one("construction.cash.receipt", string="Приходный ордер",
                                 index=True, ondelete="set null", readonly=True)


class ConstructionCashExpense(models.Model):
    _name = "construction.cash.expense"
    _inherit = ["construction.cash.doc.mixin", "mail.thread"]
    _description = "Расход кассы"
    _order = "date desc, id desc"

    name = fields.Char(string="№ ордера", readonly=True, copy=False, default="/")
    date = fields.Date(string="Дата", required=True, default=fields.Date.context_today, tracking=True)
    category = fields.Selection(EXPENSE_CATEGORIES, string="Статья", required=True,
                                default="other", tracking=True)
    recipient = fields.Char(string="Кому выдано", required=True, tracking=True)
    partner_id = fields.Many2one("res.partner", string="Контакт")
    project_id = fields.Many2one("construction.project", string="Проект",
                                 default=lambda self: self.env["construction.project"].search([], limit=1))
    method_id = fields.Many2one(
        "construction.payment.method", string="Способ", required=True,
        default=lambda self: self.env["construction.payment.method"].search([("code", "=", "cash")], limit=1))
    basis = fields.Char(string="Основание", required=True, tracking=True)
    attachment = fields.Char(string="Приложение")
    id_document = fields.Char(string="Документ получателя",
                              help="Название, номер, где и когда выдан документ получателя")
    refund_line_id = fields.Many2one("construction.refund.line", string="Выплата возврата",
                                     readonly=True, ondelete="set null")
    user_id = fields.Many2one("res.users", string="Кассир", default=lambda self: self.env.user)
    state = fields.Selection([("draft", "Черновик"), ("posted", "Проведён"), ("cancelled", "Отменён")],
                             default="draft", required=True, tracking=True, string="Статус")

    @api.onchange("project_id", "pay_currency")
    def _onchange_rate(self):
        if self.project_id and not self.exchange_rate:
            self.exchange_rate = self.project_id.usd_tjs_rate

    @api.onchange("partner_id")
    def _onchange_partner(self):
        if self.partner_id and not self.recipient:
            self.recipient = self.partner_id.name

    @api.constrains("amount", "pay_currency", "exchange_rate")
    def _check_amount(self):
        for exp in self:
            if exp.amount <= 0:
                raise ValidationError(_("Сумма расхода должна быть больше нуля."))
            if exp.pay_currency == "tjs" and exp.exchange_rate <= 0:
                raise ValidationError(_("Укажите курс USD/TJS."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.cash.expense") or "/"
            if not vals.get("exchange_rate"):
                Project = self.env["construction.project"]
                project = Project.browse(vals.get("project_id")).exists() or Project.search(
                    [("usd_tjs_rate", ">", 0)], limit=1)
                vals["exchange_rate"] = project.usd_tjs_rate or 0.0
        return super().create(vals_list)

    def write(self, vals):
        if any(e.state == "posted" for e in self) and set(vals) - {"state", "attachment", "id_document"}:
            raise UserError(_("Проведённый расход нельзя менять. Отмените его и создайте новый."))
        return super().write(vals)

    def unlink(self):
        if any(e.state == "posted" for e in self):
            raise UserError(_("Проведённый расход нельзя удалить — только отменить."))
        return super().unlink()

    def action_post(self):
        self.filtered(lambda e: e.state == "draft").write({"state": "posted"})
        return True

    def action_cancel(self):
        for exp in self:
            if exp.refund_line_id and exp.refund_line_id.paid:
                exp.refund_line_id.write({"paid": False})
        self.write({"state": "cancelled"})
        return True

    def action_draft(self):
        self.filtered(lambda e: e.state == "cancelled").write({"state": "draft"})
        return True

    def action_print_tj(self):
        return self.env.ref("construction_finance.action_report_cash_expense_tj").report_action(self)

    def action_print_ru(self):
        return self.env.ref("construction_finance.action_report_cash_expense_ru").report_action(self)


class ConstructionRefundLineExpense(models.Model):
    _inherit = "construction.refund.line"

    expense_id = fields.Many2one("construction.cash.expense", string="Расходный ордер", readonly=True)

    def action_mark_paid(self):
        res = super().action_mark_paid()
        Expense = self.env["construction.cash.expense"]
        for line in self.filtered(lambda l: l.paid and not l.expense_id):
            refund = line.refund_id
            contract = refund.contract_id
            exp = Expense.create({
                "date": line.paid_date or fields.Date.context_today(self),
                "category": "refund",
                "recipient": refund.partner_id.name,
                "partner_id": refund.partner_id.id,
                "project_id": refund.project_id.id,
                "method_id": line.method_id.id,
                "pay_currency": "usd",
                "amount": line.amount_usd,
                "basis": "Баргардонидани маблағ аз рӯи шартномаи №%s (%s), %s" % (
                    contract.number_print, contract.apartment_id.unit_code or "", refund.name),
                "refund_line_id": line.id,
            })
            exp.action_post()
            line.expense_id = exp
        return res
