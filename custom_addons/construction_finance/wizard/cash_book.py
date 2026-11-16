from markupsafe import Markup, escape

from odoo import api, fields, models

from ..models.cash_docs import EXPENSE_CATEGORIES


def _fmt(v):
    return "{:,.2f}".format(v or 0.0).replace(",", " ")


class ResCompanyCash(models.Model):
    _inherit = "res.company"

    cash_opening_date = fields.Date(string="Начало учёта кассы")
    cash_opening_tjs = fields.Float(string="Начальный остаток, сомони", digits=(16, 2))
    cash_opening_usd = fields.Float(string="Начальный остаток, USD", digits=(16, 2))


class ConstructionCashBook(models.TransientModel):
    """Кассовая книга: остаток на начало, приход, расход, остаток на конец
    — отдельно по сомони и долларам (только наличные)."""

    _name = "construction.cash.book"
    _description = "Кассовая книга"
    _rec_name = "name"

    name = fields.Char(default="Кассовая книга", readonly=True)
    date_from = fields.Date(string="С", required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string="По", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    cash_opening_date = fields.Date(related="company_id.cash_opening_date", readonly=False)
    cash_opening_tjs = fields.Float(related="company_id.cash_opening_tjs", readonly=False)
    cash_opening_usd = fields.Float(related="company_id.cash_opening_usd", readonly=False)
    book_html = fields.Html(compute="_compute_book", sanitize=False)

    # ------------------------------------------------------------------
    def _moves(self, date_from=None, date_to=None):
        """Список операций по наличным: (date, kind, doc, who, basis, tjs, usd) со знаком."""
        env = self.env
        opening = self.company_id.cash_opening_date
        dom_p = [("state", "=", "posted"), ("method_id.code", "=", "cash")]
        dom_e = [("state", "=", "posted"), ("method_id.code", "=", "cash")]
        for dom, fname in ((dom_p, "payment_date"), (dom_e, "date")):
            if opening:
                dom.append((fname, ">=", opening))
            if date_from:
                dom.append((fname, ">=", date_from))
            if date_to:
                dom.append((fname, "<=", date_to))
        moves = []
        tjs = env.ref("base.TJS")
        payments = env["construction.payment"].sudo().search(dom_p)
        seen = set()
        for pay in payments.sorted(lambda p: (p.payment_date, p.id)):
            rec = pay.receipt_id
            if rec:
                if rec.id in seen:
                    continue
                seen.add(rec.id)
                group = payments.filtered(lambda p: p.receipt_id == rec)
                doc, who, basis = "ПКО №%s" % rec.name, rec.partner_id.name, rec.basis
            else:
                group = pay
                doc, who, basis = pay.name, pay.partner_id.name, pay.schedule_id.name
            t = sum(p.amount for p in group if p.currency_id == tjs)
            u = sum(p.amount for p in group if p.currency_id != tjs)
            moves.append((pay.payment_date, "in", doc, who, basis, t, u))
        cats = dict(EXPENSE_CATEGORIES)
        for exp in env["construction.cash.expense"].sudo().search(dom_e):
            t = exp.amount if exp.pay_currency == "tjs" else 0.0
            u = exp.amount if exp.pay_currency == "usd" else 0.0
            moves.append((exp.date, "out", "РКО №%s" % exp.name, exp.recipient,
                          "%s: %s" % (cats.get(exp.category), exp.basis), -t, -u))
        moves.sort(key=lambda m: (m[0], 0 if m[1] == "in" else 1))
        return moves

    def _data(self):
        self.ensure_one()
        before = self._moves(date_to=fields.Date.subtract(self.date_from, days=1))
        open_t = self.cash_opening_tjs + sum(m[5] for m in before)
        open_u = self.cash_opening_usd + sum(m[6] for m in before)
        moves = self._moves(self.date_from, self.date_to)
        in_t = sum(m[5] for m in moves if m[1] == "in")
        in_u = sum(m[6] for m in moves if m[1] == "in")
        out_t = -sum(m[5] for m in moves if m[1] == "out")
        out_u = -sum(m[6] for m in moves if m[1] == "out")
        return {
            "open_t": open_t, "open_u": open_u, "in_t": in_t, "in_u": in_u,
            "out_t": out_t, "out_u": out_u,
            "close_t": open_t + in_t - out_t, "close_u": open_u + in_u - out_u,
            "moves": moves,
        }

    @api.depends("date_from", "date_to", "cash_opening_tjs", "cash_opening_usd", "cash_opening_date")
    def _compute_book(self):
        for book in self:
            if not book.date_from or not book.date_to:
                book.book_html = False
                continue
            d = book._data()
            card = ('<div style="flex:1;min-width:150px;border:1px solid #dee2e6;border-radius:8px;'
                    'padding:10px 14px;"><div style="color:#6c757d;font-size:12px;">%s</div>'
                    '<div style="font-size:17px;font-weight:600;">%s сом.</div>'
                    '<div style="font-size:14px;">$ %s</div></div>')
            cards = "".join(card % (escape(lbl), _fmt(t), _fmt(u)) for lbl, t, u in [
                ("Остаток на %s" % book.date_from.strftime("%d.%m.%Y"), d["open_t"], d["open_u"]),
                ("Приход", d["in_t"], d["in_u"]),
                ("Расход", d["out_t"], d["out_u"]),
                ("Остаток на %s" % book.date_to.strftime("%d.%m.%Y"), d["close_t"], d["close_u"]),
            ])
            rows = []
            run_t, run_u = d["open_t"], d["open_u"]
            for date, kind, doc, who, basis, t, u in d["moves"]:
                run_t += t
                run_u += u
                color = "#198754" if kind == "in" else "#dc3545"
                rows.append(
                    "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                    '<td style="text-align:right;color:%s;">%s</td>'
                    '<td style="text-align:right;color:%s;">%s</td>'
                    '<td style="text-align:right;">%s</td><td style="text-align:right;">%s</td></tr>' % (
                        date.strftime("%d.%m.%Y"), escape(doc), escape(who or ""), escape(basis or ""),
                        color, _fmt(t) if t else "", color, _fmt(u) if u else "",
                        _fmt(run_t), _fmt(run_u)))
            if not rows:
                rows.append('<tr><td colspan="8" style="color:#6c757d;">Нет операций за период</td></tr>')
            table = (
                '<table class="table table-sm" style="font-size:13px;margin-top:16px;">'
                "<thead><tr><th>Дата</th><th>Документ</th><th>Кто</th><th>Основание</th>"
                '<th style="text-align:right;">Сомони</th><th style="text-align:right;">USD</th>'
                '<th style="text-align:right;">Остаток сом.</th><th style="text-align:right;">Остаток $</th>'
                "</tr></thead><tbody>%s</tbody></table>" % "".join(rows))
            book.book_html = Markup(
                '<h4 style="margin:0 0 10px;">Кассовая книга (наличные) %s — %s</h4>'
                '<div style="display:flex;gap:10px;flex-wrap:wrap;">%s</div>%s' % (
                    book.date_from.strftime("%d.%m.%Y"), book.date_to.strftime("%d.%m.%Y"), cards, table))

    def action_print(self):
        return self.env.ref("construction_finance.action_report_cash_book").report_action(self)
