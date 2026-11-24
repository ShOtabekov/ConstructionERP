"""Поля и помощники для печатных форм (таджикский и русский варианты)."""
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..tools import tj_amount_words, tj_number_words

TJ_MONTHS = ["январи", "феврали", "марти", "апрели", "майи", "июни", "июли",
             "августи", "сентябри", "октябри", "ноябри", "декабри"]
RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
             "августа", "сентября", "октября", "ноября", "декабря"]

PROJECT_PRINT_DEFAULTS = {
    "seller_name_tj": "Филиали ҶДММ «Абдураҳмон Саркор» дар шаҳри Хуҷанд",
    "director_name": "Сайдуллаев Сайдуллоҷон Равшанович",
    "director_short": "Сайдуллаев С.Р.",
    "contract_city_tj": "ш. Хуҷанд",
    "object_address_tj": "шаҳри Хуҷанд, кӯчаи Б. Ёқубов",
    "seller_address_tj": "Ҷумҳурии Тоҷикистон, вилояти Суғд, ш. Хуҷанд, кӯчаи Б. Ёқубов",
    "permit_text_tj": "Қарори Раиси шаҳри Хуҷанд аз 12.02.2026 сол, таҳти №86",
    "completion_text_tj": "моҳи декабри соли 2030",
}


def tj_date(d):
    """10.09.2026 -> «10» сентябри соли 2026"""
    if not d:
        return "«___» __________ соли ____"
    return "«%02d» %s соли %s" % (d.day, TJ_MONTHS[d.month - 1], d.year)


def ru_date(d):
    if not d:
        return "«___» __________ ____ г."
    return "«%02d» %s %s г." % (d.day, RU_MONTHS[d.month - 1], d.year)


def money(v):
    return "{:,.2f}".format(v or 0).replace(",", " ").replace(".", ",")


class ResPartner(models.Model):
    _inherit = "res.partner"

    passport_series = fields.Char(string="Паспорт: серия")
    passport_number = fields.Char(string="Паспорт: номер")
    passport_issued_by = fields.Char(string="Кем выдан")
    passport_issue_date = fields.Date(string="Дата выдачи")
    residence = fields.Char(string="Место жительства")


class ConstructionProject(models.Model):
    _inherit = "construction.project"

    seller_name_tj = fields.Char(string="Продавец (тадж.)")
    director_name = fields.Char(string="Руководитель (ФИО полностью)")
    director_short = fields.Char(string="Руководитель (Фамилия И.О.)")
    contract_city_tj = fields.Char(string="Город (тадж.)")
    object_address_tj = fields.Char(string="Адрес объекта (тадж.)")
    seller_address_tj = fields.Char(string="Адрес продавца (тадж.)")
    permit_text_tj = fields.Char(string="Основание (решение хукумата)")
    completion_text_tj = fields.Char(string="Срок сдачи (тадж.)")
    chief_accountant = fields.Char(string="Главный бухгалтер")
    cashier_name = fields.Char(string="Кассир")

    @api.model
    def _fill_print_defaults(self):
        for project in self.search([]):
            vals = {k: v for k, v in PROJECT_PRINT_DEFAULTS.items() if not project[k]}
            if vals:
                project.write(vals)


class ConstructionApartment(models.Model):
    _inherit = "construction.apartment"

    unit_code = fields.Char(
        string="Код", compute="_compute_unit_code", store=True, index=True,
        help="Блок-этаж-номер на этаже, как в договорах: Д-05-07",
    )

    @api.model
    def _recompute_unit_codes(self):
        apts = self.with_context(active_test=False).search([("unit_code", "=", False)])
        apts._compute_unit_code()
        return True

    @api.depends("number", "building_id.name", "building_id.code", "floor_id.number")
    def _compute_unit_code(self):
        for apt in self:
            bname = (apt.building_id.name or "").split()
            letter = bname[-1] if bname and len(bname[-1]) <= 2 else (apt.building_id.code or "")
            digits = re.sub(r"\D", "", apt.number or "")
            floor = apt.floor_id.number or 0
            if digits and floor and digits.startswith(str(floor)) and len(digits) > len(str(floor)):
                pos = int(digits[len(str(floor)):])
                apt.unit_code = "%s-%02d-%02d" % (letter, floor, pos)
            else:
                apt.unit_code = "%s-%s" % (letter, apt.number or "")


class ConstructionContract(models.Model):
    _inherit = "construction.contract"

    name = fields.Char(readonly=False)
    number_print = fields.Char(string="№ для печати", compute="_compute_number_print")

    def _compute_number_print(self):
        """Автономер CON/2026/00094 печатается как 94, ручной номер — как введён."""
        for contract in self:
            name = contract.name or ""
            m = re.fullmatch(r"CON/\d{4}/0*(\d+)", name)
            contract.number_print = m.group(1) if m else name

    @api.model
    def _check_number_free(self, number, exclude=None):
        domain = [("name", "=", number)]
        if exclude:
            domain.append(("id", "not in", exclude.ids))
        other = self.sudo().with_context(active_test=False).search(domain, limit=1)
        if other:
            raise ValidationError(_("Договор с номером %s уже есть (%s).")
                                  % (number, other.partner_id.display_name or ""))

    @api.constrains("name")
    def _check_unique_name(self):
        for contract in self:
            if contract.name and contract.name != _("New"):
                self._check_number_free(contract.name, exclude=contract)

    # helpers for QWeb
    def _tj_words(self, amount, currency="USD"):
        return tj_amount_words(amount, currency)

    def _tj_int_words(self, n):
        return tj_number_words(n)

    def _tj_date(self, d):
        return tj_date(d)

    def _tj_money_words(self, v, currency="USD"):
        """28272.00 -> «бисту ҳашт ҳазору дусаду ҳафтоду ду»; с центами — «... ва 50 сент»."""
        v = round(v or 0.0, 2)
        whole = int(v)
        cents = int(round((v - whole) * 100))
        words = tj_number_words(whole)
        if cents:
            words += " ва %02d %s" % (cents, "сент" if currency == "USD" else "дирам")
        return words

    def _short_name(self, name):
        parts = (name or "").split()
        return " ".join(parts[:2])

    def _ru_date(self, d):
        return ru_date(d)

    def _money(self, v):
        return money(v)

    def _print_schedule(self):
        """Строки графика для Приложения 1: первый взнос отдельно, затем
        ежемесячные платежи с нарастающим итогом (как в образце)."""
        self.ensure_one()
        plan = self.payment_plan_id
        lines = plan.schedule_ids.sorted(lambda l: (l.due_date, l.id)) if plan else []
        deposit = 0.0
        rows = []
        lines = list(lines)
        if lines and plan.deposit_usd > 0:
            deposit = lines[0].amount_usd
            lines = lines[1:]
        acc = 0.0
        for i, line in enumerate(lines, 1):
            acc += line.amount_usd
            rows.append({"n": i, "date": line.due_date, "amount": line.amount_usd, "acc": acc})
        return {"deposit": deposit, "rows": rows, "rest": acc,
                "monthly": rows[0]["amount"] if rows else 0.0}


class ConstructionPaymentSchedule(models.Model):
    _inherit = "construction.payment.schedule"

    def _print_index(self):
        """0 — первый взнос, 1..N — номер ежемесячного платежа."""
        self.ensure_one()
        plan = self.plan_id
        lines = plan.schedule_ids.sorted(lambda l: (l.due_date, l.id))
        idx = list(lines.ids).index(self.id)
        return idx if plan.deposit_usd > 0 else idx + 1
