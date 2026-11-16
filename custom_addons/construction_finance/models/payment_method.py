from odoo import fields, models


class ConstructionPaymentMethod(models.Model):
    _name = "construction.payment.method"
    _description = "Construction Payment Method"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
