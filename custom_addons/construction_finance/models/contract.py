try:
    from num2words import num2words
except ImportError:  # pragma: no cover
    num2words = None

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConstructionContract(models.Model):
    _inherit = "construction.contract"

    def action_open_payment_plan(self):
        self.ensure_one()

        if self.state != "confirmed":
            raise UserError(
                _("A payment plan can only be created for a confirmed contract.")
            )

        plan = self.env["construction.payment.plan"].search(
            [("contract_id", "=", self.id)],
            limit=1
        )

        if not plan:
            plan = self.env["construction.payment.plan"].create({
                "contract_id": self.id,
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Payment Plan"),
            "res_model": "construction.payment.plan",
            "view_mode": "form",
            "res_id": plan.id,
            "target": "current",
        }

    refund_ids = fields.One2many("construction.refund", "contract_id", string="Расторжение")

    # Report fields
    unit_type = fields.Selection(related="apartment_id.unit_type", store=True, string="Тип")
    rooms = fields.Integer(related="apartment_id.rooms", store=True, string="Комнат")
    area_total = fields.Float(
        related="apartment_id.area_total", store=True, string="Площадь (м²)",
    )
    contract_price_per_sqm = fields.Monetary(
        string="Цена за м² (сделка)", currency_field="currency_usd_id",
        compute="_compute_report_prices", store=True, aggregator="avg",
    )
    list_price_usd = fields.Monetary(
        string="Цена по прайсу", currency_field="currency_usd_id", readonly=True,
        help="Цена по прайс-листу на момент продажи.",
    )
    discount_usd = fields.Monetary(
        string="Скидка от прайса", currency_field="currency_usd_id",
        compute="_compute_report_prices", store=True,
    )

    @api.depends("price_usd", "area_total", "list_price_usd")
    def _compute_report_prices(self):
        for contract in self:
            contract.contract_price_per_sqm = (
                contract.price_usd / contract.area_total if contract.area_total else 0.0
            )
            contract.discount_usd = (
                contract.list_price_usd - contract.price_usd
                if contract.list_price_usd else 0.0
            )
    payment_plan_id = fields.Many2one(
        "construction.payment.plan", string="План оплаты",
        compute="_compute_payment_plan",
    )

    def _compute_payment_plan(self):
        Plan = self.env["construction.payment.plan"].sudo()
        for contract in self:
            contract.payment_plan_id = Plan.search(
                [("contract_id", "=", contract.id)], order="id desc", limit=1,
            )

    def action_cancel(self):
        Plan = self.env["construction.payment.plan"].sudo()
        for contract in self:
            if Plan.search_count([
                ("contract_id", "=", contract.id),
                ("state", "in", ("confirmed", "closed")),
            ]):
                raise UserError(_(
                    "По договору есть план оплаты. Используйте кнопку "
                    "«Расторгнуть» — она посчитает штраф и оформит возврат."
                ))
        return super().action_cancel()

    def _cancel_for_termination(self):
        return super(ConstructionContract, self).action_cancel()

    def action_open_termination(self):
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("Расторгнуть можно только подтверждённый договор."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Расторжение договора %s") % self.name,
            "res_model": "construction.terminate.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_contract_id": self.id},
        }

    # ------------------------------------------------------------------
    # Printing helpers
    # ------------------------------------------------------------------

    @api.model
    def _amount_words(self, amount, currency="USD"):
        amount = round(amount or 0.0, 2)
        whole = int(amount)
        cents = int(round((amount - whole) * 100))
        if num2words is None:
            return ""
        try:
            words = num2words(whole, lang="ru")
        except Exception:
            return ""
        if currency == "USD":
            unit = self._plural(whole, "доллар США", "доллара США", "долларов США")
            sub = self._plural(cents, "цент", "цента", "центов")
        else:
            unit, sub = "сомони", self._plural(cents, "дирам", "дирама", "дирамов")
        return "%s %s %02d %s" % (words, unit, cents, sub)

    @staticmethod
    def _plural(n, one, few, many):
        n = abs(n) % 100
        if 11 <= n <= 14:
            return many
        n %= 10
        if n == 1:
            return one
        if 2 <= n <= 4:
            return few
        return many
