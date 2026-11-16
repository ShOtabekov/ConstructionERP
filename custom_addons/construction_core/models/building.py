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
