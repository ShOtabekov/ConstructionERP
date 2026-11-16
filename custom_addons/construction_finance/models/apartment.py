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
