from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionPriceWizard(models.TransientModel):
    """Set the price per m2 for many units at once."""

    _name = "construction.price.wizard"
    _description = "Прайс-лист"

    project_id = fields.Many2one(
        "construction.project", string="Проект", required=True,
        default=lambda self: self.env["construction.project"].search([], limit=1),
    )
    building_ids = fields.Many2many(
        "construction.building", string="Блоки",
        domain="[('project_id', '=', project_id)]",
        help="Пусто — все блоки проекта.",
    )
    unit_type = fields.Selection(
        [("apartment", "Квартиры"), ("shop", "Магазины"), ("all", "Все помещения")],
        string="Тип", default="apartment", required=True,
    )
    floor_from = fields.Integer(string="Этаж с", default=1)
    floor_to = fields.Integer(string="Этаж по", default=60)
    rooms = fields.Selection(
        [("0", "Любая"), ("1", "1К"), ("2", "2К"), ("3", "3К"), ("4", "4К и более")],
        string="Комнатность", default="0", required=True,
    )
    only_free = fields.Boolean(
        string="Только свободные", default=True,
        help="Забронированные и проданные не меняются (их цена уже зафиксирована).",
    )
    price_per_sqm_usd = fields.Float(string="Цена за м² (USD)", digits=(16, 2))
    unit_count = fields.Integer(string="Будет изменено", compute="_compute_units")
    area_total = fields.Float(string="Общая площадь (м²)", compute="_compute_units")
    total_usd = fields.Float(string="Сумма (USD)", compute="_compute_units", digits=(16, 2))

    def _domain(self):
        self.ensure_one()
        domain = [
            ("project_id", "=", self.project_id.id),
            ("floor_id.number", ">=", self.floor_from),
            ("floor_id.number", "<=", self.floor_to),
        ]
        if self.building_ids:
            domain.append(("building_id", "in", self.building_ids.ids))
        if self.unit_type != "all":
            domain.append(("unit_type", "=", self.unit_type))
        if self.rooms != "0" and self.unit_type != "shop":
            rooms = int(self.rooms)
            domain.append(("rooms", ">=", rooms) if rooms >= 4 else ("rooms", "=", rooms))
        if self.only_free:
            domain.append(("state", "in", ("free", "blocked")))
        return domain

    @api.depends("project_id", "building_ids", "unit_type", "floor_from",
                 "floor_to", "rooms", "only_free", "price_per_sqm_usd")
    def _compute_units(self):
        for wiz in self:
            if not wiz.project_id:
                wiz.unit_count = wiz.area_total = wiz.total_usd = 0
                continue
            units = self.env["construction.apartment"].search(wiz._domain())
            wiz.unit_count = len(units)
            wiz.area_total = sum(units.mapped("area_total"))
            wiz.total_usd = wiz.area_total * wiz.price_per_sqm_usd

    def action_apply(self):
        self.ensure_one()
        if self.price_per_sqm_usd <= 0:
            raise ValidationError(_("Укажите цену за м² больше нуля."))
        if self.floor_from > self.floor_to:
            raise ValidationError(_("«Этаж с» больше, чем «Этаж по»."))
        units = self.env["construction.apartment"].search(self._domain())
        if not units:
            raise UserError(_("Под условия не подходит ни одно помещение."))
        units.write({"price_per_sqm_usd": self.price_per_sqm_usd})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Цены обновлены"),
                "message": _("Изменено помещений: %s") % len(units),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
