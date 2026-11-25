from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionSaleWizard(models.TransientModel):
    """One window to sell a unit: client + unit + payment terms.

    Creates (or takes from the active reservation) the sales contract,
    confirms it, creates the payment plan with its schedule and confirms
    the plan.
    """

    _name = "construction.sale.wizard"
    _description = "Продажа квартиры"

    apartment_id = fields.Many2one(
        "construction.apartment", string="Квартира / помещение", required=True,
        domain="[('state', 'in', ('free', 'reserved'))]",
    )
    apartment_state = fields.Selection(related="apartment_id.state")
    reservation_id = fields.Many2one(
        "construction.reservation", string="Бронь",
        compute="_compute_reservation",
    )

    # Client
    partner_id = fields.Many2one("res.partner", string="Клиент")
    new_partner_name = fields.Char(string="ФИО нового клиента")
    new_partner_phone = fields.Char(string="Телефон")
    passport_series = fields.Char(string="Паспорт: серия")
    passport_number = fields.Char(string="Паспорт: номер")
    passport_issued_by = fields.Char(string="Кем выдан")
    passport_issue_date = fields.Date(string="Дата выдачи")
    residence = fields.Char(string="Место жительства")

    _PASSPORT_FIELDS = ("passport_series", "passport_number", "passport_issued_by",
                        "passport_issue_date", "residence")

    @api.onchange("partner_id")
    def _onchange_partner_passport(self):
        for fname in self._PASSPORT_FIELDS:
            self[fname] = self.partner_id[fname] if self.partner_id else False

    # Price
    currency_usd_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.ref("base.USD"),
    )
    unit_type = fields.Selection(related="apartment_id.unit_type")
    area_total = fields.Float(
        string="Площадь (м²)", compute="_compute_area_total", store=True, readonly=False,
        digits=(16, 2), help="Для магазина площадь можно изменить при оформлении.")
    contract_number = fields.Char(
        string="№ договора", help="Номер договора вручную. Пусто — номер присвоится автоматически.")
    list_price_per_sqm = fields.Float(
        string="Цена за м² по прайсу", digits=(16, 2), compute="_compute_list_price",
    )
    list_price_usd = fields.Float(
        string="Цена по прайсу (USD)", digits=(16, 2), compute="_compute_list_price",
    )
    # Deal price: filled from the price list / reservation, editable.
    deal_price_per_sqm = fields.Float(string="Цена за м² (сделка)", digits=(16, 6))
    price_usd = fields.Float(string="Цена договора (USD)", digits=(16, 2))
    discount_usd = fields.Float(
        string="Скидка (USD)", digits=(16, 2), compute="_compute_discount",
    )
    exchange_rate = fields.Float(string="Курс USD/TJS", digits=(12, 6))
    price_tjs = fields.Float(string="Цена (сомони)", compute="_compute_price_tjs", digits=(16, 2))

    # Terms
    contract_date = fields.Date(
        string="Дата договора", required=True, default=fields.Date.context_today,
    )
    payment_type = fields.Selection(
        [("installment", "Рассрочка"), ("full", "Полная оплата")],
        string="Оплата", default="installment", required=True,
    )
    deposit_mode = fields.Selection(
        [("percent", "Процент"), ("fixed", "Сумма (USD)")],
        string="Первый взнос", default="percent", required=True,
    )
    deposit_value = fields.Float(string="Взнос", default=30.0, digits=(16, 2))
    installment_count = fields.Integer(string="Количество платежей", default=12)
    schedule_interval = fields.Selection(
        [("monthly", "Ежемесячно"), ("quarterly", "Ежеквартально")],
        string="Периодичность", default="monthly", required=True,
    )
    first_payment_date = fields.Date(
        string="Первый платёж по графику",
        default=lambda self: fields.Date.context_today(self) + relativedelta(months=1),
    )
    deposit_usd = fields.Monetary(
        string="Первый взнос (USD)", currency_field="currency_usd_id",
        compute="_compute_terms",
    )
    installment_usd = fields.Monetary(
        string="Платёж (USD)", currency_field="currency_usd_id",
        compute="_compute_terms",
    )
    schedule_preview = fields.Html(
        string="График", compute="_compute_terms", sanitize=False,
    )
    notes = fields.Text(string="Примечание")

    # ------------------------------------------------------------------

    @api.depends("apartment_id", "apartment_id.state")
    def _compute_reservation(self):
        Reservation = self.env["construction.reservation"].sudo()
        for wiz in self:
            wiz.reservation_id = Reservation.search([
                ("apartment_id", "=", wiz.apartment_id.id),
                ("state", "=", "reserved"),
            ], limit=1) if wiz.apartment_id else False

    @api.onchange("apartment_id")
    def _onchange_apartment(self):
        if self.reservation_id and not self.partner_id:
            self.partner_id = self.reservation_id.partner_id

    @api.depends("apartment_id", "reservation_id")
    def _compute_area_total(self):
        for wiz in self:
            res = wiz.reservation_id.sudo()
            if wiz.apartment_id.unit_type == "shop" and res.dossier_area:
                wiz.area_total = res.dossier_area
            else:
                wiz.area_total = wiz.apartment_id.area_total

    @api.depends("apartment_id", "reservation_id", "area_total")
    def _compute_list_price(self):
        for wiz in self:
            reservation = wiz.reservation_id.sudo()
            apt = wiz.apartment_id
            if reservation and reservation.price_usd:
                wiz.list_price_usd = reservation.price_usd
            elif apt.unit_type == "shop" and apt.area_total and wiz.area_total:
                wiz.list_price_usd = round(
                    apt.total_price_usd / apt.area_total * wiz.area_total, 2)
            else:
                wiz.list_price_usd = apt.total_price_usd
            area = wiz._pricing_area() or apt.area_total
            wiz.list_price_per_sqm = wiz.list_price_usd / area if area else 0.0

    @api.depends("list_price_usd", "price_usd")
    def _compute_discount(self):
        for wiz in self:
            wiz.discount_usd = (
                round(wiz.list_price_usd - wiz.price_usd, 2)
                if wiz.list_price_usd and wiz.price_usd else 0.0
            )

    @api.depends("price_usd", "exchange_rate")
    def _compute_price_tjs(self):
        for wiz in self:
            wiz.price_tjs = round(wiz.price_usd * wiz.exchange_rate, 2)

    @api.onchange("apartment_id")
    def _onchange_apartment_price(self):
        reservation = self.reservation_id.sudo()
        self.price_usd = self.list_price_usd
        self.deal_price_per_sqm = self.list_price_per_sqm
        self.exchange_rate = (
            reservation.exchange_rate if reservation
            else self.apartment_id.usd_tjs_rate
        )
        # Бронь из досье: подставить № и дату договора и цену, как в досье
        if reservation.dossier_price_per_sqm:
            self.deal_price_per_sqm = reservation.dossier_price_per_sqm
        if reservation.price_usd:
            self.price_usd = reservation.price_usd
        if reservation.dossier_contract_no and not self.contract_number:
            self.contract_number = reservation.dossier_contract_no
        if reservation.dossier_date:
            self.contract_date = reservation.dossier_date

    def _pricing_area(self):
        """Площадь для расчёта цены: по договору из досье (старые 99,1 / 75,4), иначе текущая."""
        res = self.reservation_id.sudo()
        if res.dossier_area and self.apartment_id.unit_type != "shop":
            return res.dossier_area
        return self.area_total

    @api.onchange("area_total")
    def _onchange_area_total(self):
        area = self._pricing_area()
        if area and self.deal_price_per_sqm:
            self.price_usd = round(self.deal_price_per_sqm * area, 2)

    @api.onchange("deal_price_per_sqm")
    def _onchange_deal_price_per_sqm(self):
        area = self._pricing_area()
        if area:
            self.price_usd = round(self.deal_price_per_sqm * area, 2)

    @api.onchange("price_usd")
    def _onchange_price_usd(self):
        area = self._pricing_area()
        if area:
            per_sqm = self.price_usd / area
            if abs(per_sqm - self.deal_price_per_sqm) > 0.000001:
                self.deal_price_per_sqm = per_sqm

    def _schedule_lines(self):
        """[(label, date, amount_usd)] exactly as the plan will create them."""
        self.ensure_one()
        total = self.price_usd
        if total <= 0:
            return []
        if self.payment_type == "full":
            return [(_("Полная оплата"), self.contract_date, total)]
        usd = self.currency_usd_id or self.env.ref("base.USD")
        deposit = usd.round(self.deposit_usd)
        count = max(self.installment_count, 1)
        rest = total - deposit
        lines = []
        if deposit > 0:
            lines.append((_("Первый взнос"), self.contract_date, deposit))
        step = 1 if self.schedule_interval == "monthly" else 3
        created = 0.0
        for index in range(count):
            if index == count - 1:
                amount = usd.round(rest - created)
            else:
                amount = usd.round(rest / count)
                created += amount
            date = (self.first_payment_date or self.contract_date) + relativedelta(
                months=index * step
            )
            lines.append((_("Платёж %s") % (index + 1), date, amount))
        return lines

    @api.depends(
        "price_usd", "payment_type", "deposit_mode", "deposit_value",
        "installment_count", "schedule_interval", "first_payment_date",
        "contract_date",
    )
    def _compute_terms(self):
        for wiz in self:
            if wiz.payment_type == "full":
                wiz.deposit_usd = wiz.price_usd
            elif wiz.deposit_mode == "percent":
                wiz.deposit_usd = wiz.price_usd * wiz.deposit_value / 100.0
            else:
                wiz.deposit_usd = wiz.deposit_value
            count = max(wiz.installment_count, 1)
            wiz.installment_usd = (
                0.0 if wiz.payment_type == "full"
                else max(wiz.price_usd - wiz.deposit_usd, 0.0) / count
            )
            lines = wiz._schedule_lines() if wiz.price_usd > 0 else []
            if not lines:
                wiz.schedule_preview = False
                continue
            rows = Markup("").join(
                Markup(
                    "<tr><td>%s</td><td>%s</td>"
                    "<td class='text-end'>$ %s</td></tr>"
                ) % (
                    escape(label),
                    date.strftime("%d.%m.%Y") if date else "",
                    "{:,.2f}".format(amount).replace(",", " "),
                )
                for label, date, amount in lines
            )
            total = sum(amount for _l, _d, amount in lines)
            wiz.schedule_preview = Markup(
                "<table class='table table-sm o_sale_schedule'>"
                "<thead><tr><th>Платёж</th><th>Дата</th>"
                "<th class='text-end'>Сумма</th></tr></thead>"
                "<tbody>%s</tbody><tfoot><tr><th colspan='2'>Итого</th>"
                "<th class='text-end'>$ %s</th></tr></tfoot></table>"
            ) % (rows, "{:,.2f}".format(total).replace(",", " "))

    # ------------------------------------------------------------------

    def _check_terms(self):
        if self.price_usd <= 0:
            raise UserError(_(
                "Укажите цену договора: у помещения нет цены в прайсе — "
                "введите цену за м² или общую цену вручную."
            ))
        if self.exchange_rate <= 0:
            raise UserError(_("Укажите курс USD/TJS."))
        if self.payment_type == "installment":
            if self.installment_count < 1:
                raise ValidationError(_("Количество платежей должно быть не меньше 1."))
            if self.deposit_value < 0:
                raise ValidationError(_("Взнос не может быть отрицательным."))
            if self.deposit_usd >= self.price_usd:
                raise ValidationError(_(
                    "Первый взнос покрывает всю сумму — выберите «Полная оплата»."
                ))
            if not self.first_payment_date:
                raise ValidationError(_("Укажите дату первого платежа по графику."))
        if not self.partner_id and not (self.new_partner_name or "").strip():
            raise ValidationError(_("Выберите клиента или введите ФИО нового клиента."))

    def _get_partner(self):
        passport = {f: self[f] for f in self._PASSPORT_FIELDS if self[f]}
        if self.partner_id:
            if passport:
                self.partner_id.sudo().write(passport)
            return self.partner_id
        return self.env["res.partner"].create(dict(passport, **{
            "name": self.new_partner_name.strip(),
            "phone": (self.new_partner_phone or "").strip() or False,
        }))

    def action_sell(self):
        self.ensure_one()
        if not self.price_usd and self.list_price_usd:
            self.price_usd = self.list_price_usd
        if not self.exchange_rate:
            self.exchange_rate = (
                self.reservation_id.sudo().exchange_rate
                or self.apartment_id.usd_tjs_rate
            )
        self._check_terms()
        Contract = self.env["construction.contract"]
        Contract._check_sales_user()

        apartment = self.apartment_id
        number = (self.contract_number or "").strip()
        if number:
            Contract._check_number_free(number)
        area_note = False
        if apartment.unit_type == "shop":
            if self.area_total <= 0:
                raise ValidationError(_("Укажите площадь магазина."))
            if abs(self.area_total - apartment.area_total) > 0.001:
                area_note = _("Площадь магазина изменена при продаже: %(old)s → %(new)s м²",
                              old=apartment.area_total, new=self.area_total)
                apartment.sudo().write({"area_total": self.area_total})
        elif apartment.area_total and abs(self.area_total - apartment.area_total) > 0.001:
            raise ValidationError(_("Площадь можно менять только у магазинов."))
        partner = self._get_partner()

        if apartment.state == "reserved":
            reservation = self.reservation_id
            if not reservation:
                raise UserError(_("Квартира забронирована, но активная бронь не найдена."))
            if reservation.partner_id != partner:
                raise UserError(_(
                    "Квартира забронирована на клиента %s. Оформить договор "
                    "можно только на него (или сначала отмените бронь)."
                ) % reservation.partner_id.display_name)
            reservation.sudo(False).action_create_contract()
            contract = Contract.search([("reservation_id", "=", reservation.id)], limit=1)
            if number:
                contract.sudo().write({"name": number})
            contract.write({
                "contract_date": self.contract_date,
                "notes": self.notes,
                "price_usd": self.price_usd,
                "exchange_rate": self.exchange_rate,
            })
        elif apartment.state == "free":
            contract = Contract.create(dict({"name": number} if number else {}, **{
                "partner_id": partner.id,
                "apartment_id": apartment.id,
                "contract_date": self.contract_date,
                "notes": self.notes,
                "price_usd": self.price_usd,
                "exchange_rate": self.exchange_rate,
            }))
        else:
            raise UserError(_("Это помещение уже продано или заблокировано."))

        contract.action_confirm()
        res_d = self.reservation_id.sudo()
        if (res_d.dossier_area and apartment.unit_type != "shop"
                and abs(res_d.dossier_area - apartment.area_total) > 0.05):
            contract.sudo().write({"area_contract": res_d.dossier_area})
        if area_note:
            contract.message_post(body=area_note)
        if self.list_price_usd:
            contract.sudo().write({"list_price_usd": self.list_price_usd})
        if self.list_price_usd and abs(self.list_price_usd - self.price_usd) > 0.009:
            fmt = lambda v: "{:,.2f}".format(v).replace(",", " ")
            contract.message_post(body=_(
                "Цена договора $ %(deal)s (по прайсу $ %(list)s, разница $ %(diff)s).",
                deal=fmt(self.price_usd), list=fmt(self.list_price_usd),
                diff=fmt(self.price_usd - self.list_price_usd),
            ))

        # Payment plan: created for the seller even if he has no finance
        # rights; the plan belongs to him (user_id) and to finance.
        plan_vals = {
            "contract_id": contract.id,
            "user_id": self.env.uid,
            "date": self.contract_date,
            "schedule_interval": self.schedule_interval,
            "first_payment_date": self.first_payment_date or self.contract_date,
        }
        if self.payment_type == "full":
            plan_vals.update({
                "deposit_mode": "fixed",
                "deposit_value": 0.0,
                "installment_count": 1,
                "first_payment_date": self.contract_date,
            })
        else:
            plan_vals.update({
                "deposit_mode": self.deposit_mode,
                "deposit_value": self.deposit_value,
                "installment_count": self.installment_count,
            })
        plan = self.env["construction.payment.plan"].sudo().create(plan_vals)
        plan.action_generate_schedule()
        plan.action_confirm()

        return {
            "type": "ir.actions.act_window",
            "name": _("Договор"),
            "res_model": "construction.contract",
            "res_id": contract.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
