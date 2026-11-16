from datetime import timedelta

from odoo import fields, models, _
from odoo.exceptions import UserError


class ConstructionApartment(models.Model):
    _inherit = "construction.apartment"

    # ------------------------------------------------------------------
    # Chessboard: sales info and actions
    # ------------------------------------------------------------------

    def _chessboard_is_sales_user(self):
        user = self.env.user
        return user.has_group("base.group_system") or user.has_group(
            "construction_sales.group_sales_user"
        )

    def _chessboard_active_reservation(self):
        self.ensure_one()
        Reservation = self.env["construction.reservation"]
        if not Reservation.has_access("read"):
            return Reservation
        return Reservation.search([
            ("apartment_id", "=", self.id),
            ("state", "=", "reserved"),
        ], limit=1)

    def _chessboard_confirmed_contract(self):
        self.ensure_one()
        Contract = self.env["construction.contract"]
        if not Contract.has_access("read"):
            return Contract
        return Contract.search([
            ("apartment_id", "=", self.id),
            ("state", "=", "confirmed"),
        ], limit=1)

    def chessboard_card(self):
        card = super().chessboard_card()
        if not self._chessboard_is_sales_user():
            return card

        actions = card["actions"]
        info = card["info"]

        if self.state == "free":
            actions += [
                {
                    "method": "action_chessboard_reserve",
                    "label": _("Забронировать"),
                    "style": "primary",
                    "sequence": 10,
                },
                {
                    "method": "action_chessboard_contract",
                    "label": _("Оформить договор"),
                    "style": "success",
                    "sequence": 20,
                },
            ]

        elif self.state == "reserved":
            reservation = self._chessboard_active_reservation()
            if reservation:
                info += [
                    {"label": _("Клиент"), "value": reservation.partner_id.display_name},
                    {"label": _("Бронь"), "value": reservation.name},
                    {
                        "label": _("Бронь до"),
                        "value": fields.Datetime.context_timestamp(
                            self, reservation.date_end
                        ).strftime("%d.%m.%Y %H:%M"),
                    },
                    {"label": _("Менеджер"), "value": reservation.user_id.name},
                ]
                actions += [
                    {
                        "method": "action_chessboard_contract",
                        "label": _("Оформить договор"),
                        "style": "success",
                        "sequence": 10,
                    },
                    {
                        "method": "action_chessboard_open_reservation",
                        "label": _("Открыть бронь"),
                        "style": "secondary",
                        "sequence": 30,
                    },
                ]
            else:
                info.append({
                    "label": _("Бронь"),
                    "value": _("оформлена другим менеджером"),
                })

        elif self.state == "sold":
            contract = self._chessboard_confirmed_contract()
            if contract:
                info += [
                    {"label": _("Клиент"), "value": contract.partner_id.display_name},
                    {"label": _("Договор"), "value": contract.name},
                    {
                        "label": _("Дата договора"),
                        "value": contract.contract_date.strftime("%d.%m.%Y"),
                    },
                    {
                        "label": _("Цена по договору"),
                        "value": "$ {:,.2f}".format(contract.price_usd).replace(",", " "),
                    },
                    {"label": _("Менеджер"), "value": contract.user_id.name},
                ]
                actions.append({
                    "method": "action_chessboard_open_contract",
                    "label": _("Открыть договор"),
                    "style": "secondary",
                    "sequence": 30,
                })
            else:
                info.append({
                    "label": _("Договор"),
                    "value": _("оформлен другим менеджером"),
                })

        return card

    def action_chessboard_reserve(self):
        self.ensure_one()
        if self.state != "free":
            raise UserError(_("Забронировать можно только свободную квартиру."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Новая бронь"),
            "res_model": "construction.reservation",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
            "context": {
                "default_apartment_id": self.id,
                "default_date_end": fields.Datetime.to_string(
                    fields.Datetime.now() + timedelta(days=3)
                ),
            },
        }

    def action_chessboard_contract(self):
        self.ensure_one()
        if self.state == "reserved":
            reservation = self._chessboard_active_reservation()
            if not reservation:
                raise UserError(
                    _("Квартира забронирована другим менеджером.")
                )
            return reservation.action_create_contract()

        if self.state != "free":
            raise UserError(
                _("Договор можно оформить только на свободную или забронированную квартиру.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Новый договор"),
            "res_model": "construction.contract",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
            "context": {"default_apartment_id": self.id},
        }

    def action_chessboard_open_reservation(self):
        self.ensure_one()
        reservation = self._chessboard_active_reservation()
        if not reservation:
            raise UserError(_("Активная бронь не найдена."))
        return {
            "type": "ir.actions.act_window",
            "name": reservation.name,
            "res_model": "construction.reservation",
            "res_id": reservation.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_chessboard_open_contract(self):
        self.ensure_one()
        contract = self._chessboard_confirmed_contract()
        if not contract:
            raise UserError(_("Подтверждённый договор не найден."))
        return {
            "type": "ir.actions.act_window",
            "name": contract.name,
            "res_model": "construction.contract",
            "res_id": contract.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
