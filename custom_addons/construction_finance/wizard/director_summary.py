from collections import OrderedDict

from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

from odoo import _, api, fields, models


def _plural(n, one, few, many):
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


def _fmt(value, digits=2):
    return ("{:,.%df}" % digits).format(value or 0.0).replace(",", " ")


class ConstructionDirectorSummary(models.TransientModel):
    """One page with the key figures for a period (screen + PDF)."""

    _name = "construction.director.summary"
    _description = "Сводка директора"

    date_from = fields.Date(
        string="С", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="По", required=True, default=fields.Date.context_today,
    )
    project_id = fields.Many2one("construction.project", string="Проект")
    summary_html = fields.Html(compute="_compute_summary", sanitize=False)

    # ------------------------------------------------------------------

    def _domain(self, project_field="project_id"):
        return [(project_field, "=", self.project_id.id)] if self.project_id else []

    def _data(self):
        self.ensure_one()
        env = self.env
        today = fields.Date.context_today(self)
        Apartment = env["construction.apartment"].sudo()
        Contract = env["construction.contract"].sudo()
        Payment = env["construction.payment"].sudo()
        Plan = env["construction.payment.plan"].sudo()
        Schedule = env["construction.payment.schedule"].sudo()
        Refund = env["construction.refund"].sudo()

        units = Apartment.search(self._domain())
        stock = OrderedDict()
        for state, label in [("free", "Свободно"), ("reserved", "Бронь"),
                             ("sold", "Продано"), ("blocked", "Заблокировано")]:
            group = units.filtered(lambda u: u.state == state)
            stock[label] = (len(group), sum(group.mapped("area_total")),
                            sum(group.mapped("total_price_usd")))

        contracts = Contract.search(self._domain() + [
            ("state", "=", "confirmed"),
            ("contract_date", ">=", self.date_from),
            ("contract_date", "<=", self.date_to),
        ])
        sold_area = sum(contracts.mapped("area_total"))
        sold_sum = sum(contracts.mapped("price_usd"))

        payments = Payment.search(self._domain() + [
            ("state", "=", "posted"),
            ("payment_date", ">=", self.date_from),
            ("payment_date", "<=", self.date_to),
        ])
        by_method = OrderedDict()
        for payment in payments:
            key = payment.method_id.name or "—"
            by_method[key] = by_method.get(key, 0.0) + payment.amount_usd

        plans = Plan.search(self._domain() + [("state", "=", "confirmed")])
        debt = {
            "total": sum(plans.mapped("balance_usd")),
            "overdue": sum(plans.mapped("overdue_usd")),
            "b1": sum(plans.mapped("overdue_0_30")),
            "b2": sum(plans.mapped("overdue_31_60")),
            "b3": sum(plans.mapped("overdue_61_90")),
            "b4": sum(plans.mapped("overdue_90")),
            "debtors": len(plans.filtered(lambda p: p.overdue_usd > 0)),
        }

        forecast = OrderedDict()
        start = today.replace(day=1)
        lines = Schedule.search(self._domain() + [
            ("plan_id.state", "=", "confirmed"),
            ("balance_usd", ">", 0),
            ("due_date", ">=", today),
            ("due_date", "<", start + relativedelta(months=6)),
        ])
        for month in range(6):
            month_start = start + relativedelta(months=month)
            month_end = month_start + relativedelta(months=1)
            forecast[month_start.strftime("%m.%Y")] = sum(
                l.balance_usd for l in lines
                if month_start <= l.due_date < month_end
            )

        refunds = Refund.search(self._domain() + [
            ("date", ">=", self.date_from), ("date", "<=", self.date_to),
        ])
        all_open_refunds = Refund.search(self._domain() + [("state", "=", "open")])
        refund = {
            "count": len(refunds),
            "penalty": sum(refunds.mapped("penalty_usd")),
            "refund": sum(refunds.mapped("refund_usd")),
            "to_pay": sum(all_open_refunds.mapped("remaining_usd")),
        }
        return {
            "stock": stock, "units": len(units),
            "sales": (len(contracts), sold_area, sold_sum,
                      sold_sum / sold_area if sold_area else 0.0,
                      sum(contracts.mapped("discount_usd"))),
            "received": sum(payments.mapped("amount_usd")),
            "payments": len(payments), "by_method": by_method,
            "debt": debt, "forecast": forecast, "refund": refund,
        }

    @api.depends("date_from", "date_to", "project_id")
    def _compute_summary(self):
        for wiz in self:
            if not (wiz.date_from and wiz.date_to):
                wiz.summary_html = False
                continue
            d = wiz._data()

            def table(head, rows, total=None):
                h = Markup("").join(Markup("<th>%s</th>") % c for c in head)
                body = Markup("").join(
                    Markup("<tr>") + Markup("").join(
                        Markup("<td>%s</td>") % c for c in row) + Markup("</tr>")
                    for row in rows
                )
                foot = Markup("")
                if total:
                    foot = Markup("<tfoot><tr>") + Markup("").join(
                        Markup("<th>%s</th>") % c for c in total) + Markup("</tr></tfoot>")
                return Markup(
                    "<table class='table table-sm table-bordered o_dir_table'>"
                    "<thead><tr>%s</tr></thead><tbody>%s</tbody>%s</table>"
                ) % (h, body, foot)

            def card(title, value, note=""):
                return Markup(
                    "<div class='col-6 col-md-3 mb-3'><div class='border rounded p-3 h-100'>"
                    "<div class='text-muted small'>%s</div><div class='fs-4 fw-bold'>%s</div>"
                    "<div class='small text-muted'>%s</div></div></div>"
                ) % (title, value, note)

            sales = d["sales"]
            debt = d["debt"]
            ref = d["refund"]
            cards = Markup("<div class='row'>%s%s%s%s</div>") % (
                card("Продано за период", "$ " + _fmt(sales[2], 0),
                     "%s %s, %s м²" % (sales[0], _plural(sales[0], "договор", "договора", "договоров"), _fmt(sales[1], 1))),
                card("Поступило за период", "$ " + _fmt(d["received"], 0),
                     "%s %s" % (d["payments"], _plural(d["payments"], "платёж", "платежа", "платежей"))),
                card("Долг клиентов всего", "$ " + _fmt(debt["total"], 0),
                     "по действующим договорам"),
                card("Просрочено", "$ " + _fmt(debt["overdue"], 0),
                     "%s %s" % (debt["debtors"], _plural(debt["debtors"], "должник", "должника", "должников"))),
            )
            stock_rows = [
                (label, cnt, _fmt(area, 1), "$ " + _fmt(val, 0))
                for label, (cnt, area, val) in d["stock"].items()
            ]
            total_cnt = sum(v[0] for v in d["stock"].values())
            total_area = sum(v[1] for v in d["stock"].values())
            stock_tbl = table(["Статус", "Помещений", "Площадь, м²", "По прайсу"],
                              stock_rows, ["Итого", total_cnt, _fmt(total_area, 1), ""])
            sales_tbl = table(
                ["Договоров", "Площадь, м²", "Сумма", "Средняя цена м²", "Скидки от прайса"],
                [(sales[0], _fmt(sales[1], 1), "$ " + _fmt(sales[2]),
                  "$ " + _fmt(sales[3]), "$ " + _fmt(sales[4]))])
            method_tbl = table(["Способ оплаты", "Сумма, USD"],
                               [(k, _fmt(v)) for k, v in d["by_method"].items()] or [("—", "0.00")],
                               ["Итого", _fmt(d["received"])])
            aging_tbl = table(["1–30 дн.", "31–60 дн.", "61–90 дн.", "Более 90 дн.", "Всего просрочено"],
                              [(_fmt(debt["b1"]), _fmt(debt["b2"]), _fmt(debt["b3"]),
                                _fmt(debt["b4"]), _fmt(debt["overdue"]))])
            fc_tbl = table(list(d["forecast"].keys()) + ["Итого"],
                           [[_fmt(v, 0) for v in d["forecast"].values()]
                            + [_fmt(sum(d["forecast"].values()), 0)]])
            ref_tbl = table(["Расторжений", "Удержано штрафов", "К возврату", "Ещё выплатить (все)"],
                            [(ref["count"], _fmt(ref["penalty"]), _fmt(ref["refund"]), _fmt(ref["to_pay"]))])
            title = Markup("<h3>Сводка за %s — %s%s</h3>") % (
                wiz.date_from.strftime("%d.%m.%Y"), wiz.date_to.strftime("%d.%m.%Y"),
                Markup(" · %s") % escape(wiz.project_id.name) if wiz.project_id else "")
            h = lambda text: Markup("<h5 class='mt-4'>%s</h5>") % text
            wiz.summary_html = (
                title + cards
                + h("Остатки помещений (сейчас)") + stock_tbl
                + h("Продажи за период") + sales_tbl
                + h("Поступления за период") + method_tbl
                + h("Просрочка по срокам (сейчас)") + aging_tbl
                + h("Прогноз поступлений по графикам, USD (ближайшие 6 месяцев)") + fc_tbl
                + h("Расторжения за период") + ref_tbl
            )

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            "construction_finance.action_report_director_summary"
        ).report_action(self)
