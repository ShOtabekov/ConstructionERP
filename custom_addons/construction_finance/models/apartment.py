from odoo import models, _
from odoo.exceptions import UserError


class ConstructionApartment(models.Model):
    _inherit = "construction.apartment"

    def _chessboard_is_finance_user(self):
        user = self.env.user
        return user.has_group("base.group_system") or user.has_group(
            "construction_finance.group_finance_user"
        )

    def chessboard_card(self):
        card = super().chessboard_card()
        if self.state in ("free", "reserved") and self._chessboard_is_sales_user():
            # One-window sale replaces the old "create contract" button.
            card["actions"] = [
                act for act in card["actions"]
                if act["method"] != "action_chessboard_contract"
            ]
            card["actions"].append({
                "method": "action_chessboard_sell",
                "label": _("Продать"),
                "style": "success",
                "sequence": 5,
            })
        if self.state != "sold" or not self._chessboard_is_finance_user():
            return card

        Plan = self.env["construction.payment.plan"]
        if not Plan.has_access("read"):
            return card

        plan = Plan.search([
            ("apartment_id", "=", self.id),
            ("state", "in", ("draft", "confirmed", "closed")),
        ], limit=1)
        if plan:
            state_labels = dict(
                Plan._fields["state"]._description_selection(self.env)
            )
            fmt = lambda v: "$ {:,.2f}".format(v).replace(",", " ")
            card["info"] += [
                {"label": _("План оплаты"), "value": "%s (%s)" % (
                    plan.name, state_labels.get(plan.state, plan.state))},
                {"label": _("Оплачено"), "value": fmt(plan.paid_usd)},
                {"label": _("Остаток"), "value": fmt(plan.balance_usd)},
            ]

        if self._chessboard_confirmed_contract():
            card["actions"].append({
                "method": "action_chessboard_cash",
                "label": _("Принять платёж"),
                "style": "success",
                "sequence": 10,
            })
            if self.env.user.has_group("construction_finance.group_finance_manager"):
                card["actions"].append({
                    "method": "action_chessboard_terminate",
                    "label": _("Расторгнуть"),
                    "style": "secondary",
                    "sequence": 70,
                })
            card["actions"].append({
                "method": "action_chessboard_payment_plan",
                "label": _("План оплаты"),
                "style": "primary",
                "sequence": 20,
            })
        return card

    def action_chessboard_payment_plan(self):
        self.ensure_one()
        contract = self._chessboard_confirmed_contract()
        if not contract:
            raise UserError(_("Подтверждённый договор не найден."))
        return contract.action_open_payment_plan()

    def action_chessboard_sell(self):
        self.ensure_one()
        if self.state not in ("free", "reserved"):
            raise UserError(_("Продать можно только свободное или забронированное помещение."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Продажа: %s") % self.name,
            "res_model": "construction.sale.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_apartment_id": self.id},
        }

    def action_chessboard_cash(self):
        self.ensure_one()
        contract = self._chessboard_confirmed_contract()
        if not contract:
            raise UserError(_("Подтверждённый договор не найден."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Принять платёж: %s") % self.name,
            "res_model": "construction.cash.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_partner_id": contract.partner_id.id,
                "default_contract_id": contract.id,
            },
        }

    def action_chessboard_terminate(self):
        self.ensure_one()
        contract = self._chessboard_confirmed_contract()
        if not contract:
            raise UserError(_("Подтверждённый договор не найден."))
        return contract.action_open_termination()
