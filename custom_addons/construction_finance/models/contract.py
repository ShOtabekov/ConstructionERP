from odoo import models, _
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
