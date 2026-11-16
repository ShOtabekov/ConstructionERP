import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import file_open

from .rahmoniyon_preset import (
    RAHMONIYON_BLOCKS,
    RAHMONIYON_DEFAULTS,
    unit_image_path,
)

PRESET_SELECTION = [("custom", "Manual")] + [
    (key, "Rahmoniyon — %s" % data["name"])
    for key, data in RAHMONIYON_BLOCKS.items()
] + [("all", "Rahmoniyon — all 5 blocks")]


class ConstructionBlockWizard(models.TransientModel):
    """Create a whole block: building, entrance, floors, shops, apartments."""

    _name = "construction.block.wizard"
    _description = "Create Block"

    project_id = fields.Many2one(
        "construction.project", string="Project", required=True,
        default=lambda self: self.env.context.get("default_project_id")
        or self.env["construction.project"].search([], limit=1),
    )
    preset = fields.Selection(
        PRESET_SELECTION, string="Template", default="custom", required=True,
    )
    name = fields.Char(string="Block Name")
    code = fields.Char(string="Block Code")
    floors_total = fields.Integer(string="Floors", default=20)
    residential_from = fields.Integer(
        string="Apartments From Floor", default=2,
        help="Floors below this one have no apartments.",
    )
    shop_count = fields.Integer(string="Shops on 1st Floor", default=5)
    shop_area = fields.Float(string="Shop Area (m2)", default=100.0)
    price_per_sqm_usd = fields.Float(string="Apartment Price per m2 (USD)")
    shop_price_per_sqm_usd = fields.Float(string="Shop Price per m2 (USD)")
    numbering = fields.Selection(
        [
            ("floor", "By floor: 201, 202 … 2001"),
            ("through", "Through the block: 1, 2, 3 …"),
        ],
        string="Numbering", default="floor", required=True,
    )
    floor_plan_image = fields.Image(string="Typical Floor Plan")
    line_ids = fields.One2many(
        "construction.block.wizard.line", "wizard_id", string="Floor Layout",
    )
    summary = fields.Char(compute="_compute_summary")

    # ------------------------------------------------------------------

    @api.depends("preset", "line_ids", "floors_total", "residential_from",
                 "shop_count")
    def _compute_summary(self):
        for wiz in self:
            floors = max(wiz.floors_total - wiz.residential_from + 1, 0)
            if wiz.preset == "all":
                per_floor = sum(len(b["units"]) for b in RAHMONIYON_BLOCKS.values())
                blocks = len(RAHMONIYON_BLOCKS)
            else:
                per_floor = len(wiz.line_ids)
                blocks = 1
            wiz.summary = _(
                "%(blocks)s block(s): %(apartments)s apartments + %(shops)s shops",
                blocks=blocks,
                apartments=per_floor * floors,
                shops=wiz.shop_count * blocks,
            )

    @staticmethod
    def _preset_image(path):
        with file_open(path, "rb") as image:
            return base64.b64encode(image.read())

    @api.onchange("preset")
    def _onchange_preset(self):
        if self.preset in (False, "custom"):
            return
        self.update(RAHMONIYON_DEFAULTS)
        if self.preset == "all":
            self.name = False
            self.code = False
            self.line_ids = [(5, 0, 0)]
            self.floor_plan_image = False
            return
        data = RAHMONIYON_BLOCKS[self.preset]
        self.name = data["name"]
        self.code = data["code"]
        self.floor_plan_image = self._preset_image(data["image"])
        self.line_ids = [(5, 0, 0)] + [
            (0, 0, {
                "sequence": index,
                "rooms": rooms,
                "area_total": area,
                "plan_x": x,
                "plan_y": y,
                "plan_image": self._preset_image(
                    unit_image_path(self.preset, index)
                ),
            })
            for index, (rooms, area, x, y) in enumerate(data["units"], 1)
        ]

    # ------------------------------------------------------------------

    def _check_values(self):
        if self.floors_total < 1 or self.floors_total > 60:
            raise ValidationError(_("Number of floors must be between 1 and 60."))
        if self.residential_from < 1 or self.residential_from > self.floors_total:
            raise ValidationError(_("Check the first apartment floor."))
        if self.shop_count < 0 or (self.shop_count and self.shop_area <= 0):
            raise ValidationError(_("Check the number and area of shops."))

    def _block_specs(self):
        """List of blocks to create: dicts with name/code/image/units."""
        if self.preset == "all":
            return [
                {
                    "name": data["name"],
                    "code": data["code"],
                    "image": self._preset_image(data["image"]),
                    "units": data["units"],
                    "unit_images": [
                        self._preset_image(unit_image_path(key, index))
                        for index in range(1, len(data["units"]) + 1)
                    ],
                }
                for key, data in RAHMONIYON_BLOCKS.items()
            ]
        if not self.name or not self.code:
            raise ValidationError(_("Enter the block name and code."))
        if not self.line_ids:
            raise ValidationError(_("Add at least one apartment to the floor layout."))
        return [{
            "name": self.name,
            "code": self.code,
            "image": self.floor_plan_image,
            "units": [
                (line.rooms, line.area_total, line.plan_x, line.plan_y)
                for line in self.line_ids.sorted("sequence")
            ],
            "unit_images": [
                line.plan_image for line in self.line_ids.sorted("sequence")
            ],
        }]

    def _create_block(self, spec):
        Building = self.env["construction.building"]
        if Building.with_context(active_test=False).search_count([
            ("project_id", "=", self.project_id.id),
            ("code", "=", spec["code"]),
        ]):
            raise UserError(
                _("Block with code %s already exists in this project.") % spec["code"]
            )
        for rooms, area, _x, _y in spec["units"]:
            if area <= 0 or rooms < 1:
                raise ValidationError(_("Every apartment needs rooms and an area."))

        building = Building.create({
            "name": spec["name"],
            "code": spec["code"],
            "project_id": self.project_id.id,
            "floor_plan_image": spec["image"] or False,
        })
        unit_images = spec.get("unit_images") or []
        layouts = self.env["construction.unit.layout"].create([
            {
                "building_id": building.id,
                "sequence": index,
                "rooms": rooms,
                "area_total": area,
                "plan_x": x,
                "plan_y": y,
                "plan_image": (
                    unit_images[index - 1]
                    if index <= len(unit_images) else False
                ) or False,
            }
            for index, (rooms, area, x, y) in enumerate(spec["units"], 1)
        ])
        entrance = self.env["construction.entrance"].create({
            "name": "Подъезд 1",
            "code": "1",
            "building_id": building.id,
        })
        floors = self.env["construction.floor"].create([
            {"number": number, "entrance_id": entrance.id}
            for number in range(1, self.floors_total + 1)
        ])

        units = []
        counter = 0
        for floor in floors:
            if floor.number == 1 and self.shop_count:
                for index in range(1, self.shop_count + 1):
                    units.append({
                        "floor_id": floor.id,
                        "unit_type": "shop",
                        "number": (
                            "%d%02d" % (floor.number, index)
                            if self.numbering == "floor" else "M%d" % index
                        ),
                        "rooms": 0,
                        "area_total": self.shop_area,
                        "price_per_sqm_usd": self.shop_price_per_sqm_usd,
                    })
            if floor.number < self.residential_from:
                continue
            for layout in layouts:
                counter += 1
                units.append({
                    "floor_id": floor.id,
                    "unit_type": "apartment",
                    "layout_id": layout.id,
                    "number": (
                        "%d%02d" % (floor.number, layout.sequence)
                        if self.numbering == "floor" else str(counter)
                    ),
                    "rooms": layout.rooms,
                    "area_total": layout.area_total,
                    "price_per_sqm_usd": self.price_per_sqm_usd,
                })
        self.env["construction.apartment"].create(units)
        return building

    def action_generate(self):
        self.ensure_one()
        self._check_values()
        buildings = self.env["construction.building"]
        for spec in self._block_specs():
            buildings |= self._create_block(spec)
        return {
            "type": "ir.actions.client",
            "tag": "construction_apartment_chessboard",
            "name": _("Chessboard"),
        }


class ConstructionBlockWizardLine(models.TransientModel):
    _name = "construction.block.wizard.line"
    _description = "Create Block: Floor Layout Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "construction.block.wizard", required=True, ondelete="cascade",
    )
    sequence = fields.Integer(string="Position", default=1)
    rooms = fields.Integer(string="Rooms", default=1)
    area_total = fields.Float(string="Total Area (m2)", digits=(12, 2))
    plan_x = fields.Float(string="Plan X (%)", digits=(5, 2))
    plan_y = fields.Float(string="Plan Y (%)", digits=(5, 2))
    plan_image = fields.Image(string="Unit Plan")
