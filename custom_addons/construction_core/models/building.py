import base64

from odoo import api, fields, models
from odoo.tools import file_open


class ConstructionBuilding(models.Model):
    _name = "construction.building"
    _description = "Construction Building"
    _order = "project_id, name"

    name = fields.Char(string="Building Name", required=True)
    code = fields.Char(string="Building Code", required=True)
    project_id = fields.Many2one(
        "construction.project",
        string="Project",
        required=True,
        ondelete="cascade",
    )
    address = fields.Char(string="Address")
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)

    floor_plan_image = fields.Image(
        string="Typical Floor Plan",
        max_width=2400,
        max_height=2400,
    )
    layout_ids = fields.One2many(
        "construction.unit.layout",
        "building_id",
        string="Floor Layout",
    )

    @api.model
    def _fill_rahmoniyon_unit_plans(self):
        """Add per-unit plan images to Rahmoniyon blocks created earlier.

        A block matches when its code and its floor layout (rooms and
        areas, in order) are exactly the preset ones. Existing images
        are never overwritten.
        """
        from ..wizard.rahmoniyon_preset import RAHMONIYON_BLOCKS, unit_image_path

        for key, data in RAHMONIYON_BLOCKS.items():
            expected = [(rooms, area) for rooms, area, _x, _y in data["units"]]
            for building in self.with_context(active_test=False).search(
                [("code", "=", data["code"])]
            ):
                layouts = building.layout_ids.sorted("sequence")
                actual = [(l.rooms, round(l.area_total, 1)) for l in layouts]
                if actual != expected:
                    continue
                for index, layout in enumerate(layouts, 1):
                    if layout.plan_image:
                        continue
                    with file_open(unit_image_path(key, index), "rb") as image:
                        layout.plan_image = base64.b64encode(image.read())
        return True

    @api.model
    def _refresh_rahmoniyon_plans(self):
        """Заменить картинки планов этажей и квартир Rahmoniyon новой версией
        (площади не трогаются). Выполняется один раз на каждую версию планов."""
        from ..wizard.rahmoniyon_preset import (
            RAHMONIYON_BLOCKS, RAHMONIYON_PLANS_VERSION, unit_image_path)
        ICP = self.env["ir.config_parameter"].sudo()
        if ICP.get_param("construction_core.rahmoniyon_plans") == RAHMONIYON_PLANS_VERSION:
            return True

        def read_img(path):
            with file_open(path, "rb") as f:
                return base64.b64encode(f.read())

        for key, data in RAHMONIYON_BLOCKS.items():
            for building in self.with_context(active_test=False).search([("code", "=", data["code"])]):
                if not building.project_id.name or "rahmoniyon" not in building.project_id.name.lower():
                    continue
                building.floor_plan_image = read_img(data["image"])
                layouts = building.layout_ids.sorted("sequence")
                if len(layouts) != len(data["units"]):
                    continue
                for i, (layout, (_r, _a, x, y)) in enumerate(zip(layouts, data["units"]), 1):
                    layout.write({"plan_x": x, "plan_y": y,
                                  "plan_image": read_img(unit_image_path(key, i))})
        ICP.set_param("construction_core.rahmoniyon_plans", RAHMONIYON_PLANS_VERSION)
        return True

    # ------------------------------------------------------------------
    # 19.0.1.9.0: квартиры ЖК Rahmoniyon по списку застройщика
    # ------------------------------------------------------------------
    @api.model
    def _sync_rahmoniyon_layouts(self):
        """Привести блоки Rahmoniyon к списку квартир застройщика.

        * Тот же состав квартир на этаже — меняются только площади
          (в свободных/заблокированных квартирах).
        * Другое число квартир на этаже (блок Д: 6 -> 8) — блок
          перестраивается, только если все его квартиры свободны и на них
          нет броней и договоров. Иначе блок не трогаем и пишем в лог.
        """
        import logging
        from ..wizard.rahmoniyon_preset import RAHMONIYON_BLOCKS, unit_image_path

        _logger = logging.getLogger(__name__)
        Apartment = self.env["construction.apartment"].with_context(active_test=False)
        Layout = self.env["construction.unit.layout"]

        def read_img(path):
            with file_open(path, "rb") as f:
                return base64.b64encode(f.read())

        for key, data in RAHMONIYON_BLOCKS.items():
            expected = data["units"]
            for building in self.with_context(active_test=False).search([("code", "=", data["code"])]):
                if not building.project_id.name or "rahmoniyon" not in building.project_id.name.lower():
                    continue
                layouts = building.layout_ids.sorted("sequence")
                actual = [(l.rooms, round(l.area_total, 1)) for l in layouts]
                wanted = [(r, a) for r, a, _x, _y in expected]
                if actual == wanted:
                    continue
                units = Apartment.search([("building_id", "=", building.id), ("unit_type", "!=", "shop")])
                if len(layouts) == len(expected):
                    for layout, (rooms, area, _x, _y) in zip(layouts, expected):
                        if (layout.rooms, round(layout.area_total, 1)) == (rooms, area):
                            continue
                        layout.write({"rooms": rooms, "area_total": area})
                        todo = units.filtered(lambda u: u.layout_id == layout)
                        busy = todo.filtered(lambda u: u.state in ("reserved", "sold"))
                        if busy:
                            _logger.warning("Rahmoniyon %s: площадь не изменена у занятых квартир %s",
                                            building.name, ", ".join(busy.mapped("number")))
                        (todo - busy).write({"rooms": rooms, "area_total": area})
                    continue

                # Другое число квартир на этаже — перестроить, если блок свободен
                if units.filtered(lambda u: u.state != "free"):
                    _logger.warning("Rahmoniyon %s: блок не перестроен — есть занятые квартиры", building.name)
                    continue
                for model in ("construction.reservation", "construction.contract"):
                    if model in self.env and "apartment_id" in self.env[model]._fields and \
                            self.env[model].sudo().with_context(active_test=False).search_count(
                                [("apartment_id", "in", units.ids)]):
                        _logger.warning("Rahmoniyon %s: блок не перестроен — есть %s", building.name, model)
                        break
                else:
                    floors = units.mapped("floor_id").sorted("number")
                    price = max(units.mapped("price_per_sqm_usd") or [0.0])
                    units.unlink()
                    layouts.unlink()
                    new_layouts = Layout.create([{
                        "building_id": building.id,
                        "sequence": i,
                        "rooms": rooms,
                        "area_total": area,
                        "plan_x": x,
                        "plan_y": y,
                        "plan_image": read_img(unit_image_path(key, i)),
                    } for i, (rooms, area, x, y) in enumerate(expected, 1)])
                    building.floor_plan_image = read_img(data["image"])
                    Apartment.create([{
                        "floor_id": floor.id,
                        "unit_type": "apartment",
                        "layout_id": layout.id,
                        "number": "%d%02d" % (floor.number, layout.sequence),
                        "rooms": layout.rooms,
                        "area_total": layout.area_total,
                        "price_per_sqm_usd": price,
                    } for floor in floors for layout in new_layouts])
                    _logger.info("Rahmoniyon %s: перестроен, %d квартир", building.name,
                                 len(floors) * len(new_layouts))
        return True
