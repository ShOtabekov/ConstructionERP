from odoo import fields, models


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
