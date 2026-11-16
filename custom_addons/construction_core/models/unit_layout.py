from odoo import api, fields, models


class ConstructionUnitLayout(models.Model):
    """A unit position on the typical floor plan of a block.

    Every residential floor of a block repeats the same layouts; each
    apartment points to its layout, which gives its place on the plan.
    """

    _name = "construction.unit.layout"
    _description = "Unit Layout"
    _order = "building_id, sequence, id"

    building_id = fields.Many2one(
        "construction.building",
        string="Building",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Position", default=1)
    name = fields.Char(compute="_compute_name", store=True)
    unit_type = fields.Selection(
        [("apartment", "Apartment"), ("shop", "Shop")],
        string="Unit Type",
        default="apartment",
        required=True,
    )
    rooms = fields.Integer(string="Rooms", default=1)
    area_total = fields.Float(string="Total Area (m2)", digits=(12, 2))
    plan_x = fields.Float(
        string="Plan X (%)",
        digits=(5, 2),
        help="Horizontal position of the unit on the floor plan, 0-100 %.",
    )
    plan_y = fields.Float(
        string="Plan Y (%)",
        digits=(5, 2),
        help="Vertical position of the unit on the floor plan, 0-100 %.",
    )
    apartment_ids = fields.One2many(
        "construction.apartment", "layout_id", string="Units"
    )
    apartment_count = fields.Integer(compute="_compute_apartment_count")

    @api.depends("sequence", "rooms", "area_total", "unit_type")
    def _compute_name(self):
        for layout in self:
            if layout.unit_type == "shop":
                kind = "Маг."
            else:
                kind = f"{layout.rooms}К"
            layout.name = f"№{layout.sequence} · {kind} · {layout.area_total:g} м²"

    def _compute_apartment_count(self):
        for layout in self:
            layout.apartment_count = len(layout.apartment_ids)
