from odoo import api, fields, models


class ConstructionPaymentMethod(models.Model):
    _name = "construction.payment.method"
    _description = "Construction Payment Method"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()

    @api.model
    def _ensure_defaults(self):
        """На чистой базе нет ни одного способа оплаты — создаём «Наличные» и «Перевод»."""
        for code, name, seq in (("cash", "Наличные", 1), ("bank", "Перевод", 2)):
            if not self.with_context(active_test=False).search_count([("code", "=", code)]):
                self.create({"name": name, "code": code, "sequence": seq})
        return True
