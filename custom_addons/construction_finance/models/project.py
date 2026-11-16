from odoo import fields, models

PENALTY_MODES = [
    ("paid_percent", "% от внесённой суммы"),
    ("price_percent", "% от цены договора"),
    ("fixed", "Фиксированная сумма (USD)"),
    ("none", "Без штрафа"),
]


class ConstructionProject(models.Model):
    _inherit = "construction.project"

    termination_penalty_mode = fields.Selection(
        PENALTY_MODES, string="Штраф при расторжении",
        default="paid_percent", required=True,
    )
    termination_penalty_value = fields.Float(
        string="Размер штрафа", default=10.0, digits=(16, 2),
        help="Процент или сумма в USD — в зависимости от типа штрафа. "
             "Используется по умолчанию, при расторжении можно изменить.",
    )
