from odoo import fields, models


class ConstructionReservation(models.Model):
    """Данные из досье застройщика: при «Продать» из этой брони они подставятся
    в окно продажи (№ и дата договора, цена, площадь по договору)."""

    _inherit = "construction.reservation"

    dossier_contract_no = fields.Char("№ договора (досье)", copy=False)
    dossier_date = fields.Date("Дата договора (досье)", copy=False)
    dossier_price_per_sqm = fields.Float("Цена за м² (досье)", digits=(16, 2), copy=False)
    dossier_area = fields.Float("Площадь по договору (досье)", digits=(16, 2), copy=False)
