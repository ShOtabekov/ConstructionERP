from odoo import models, fields


class ConstructionEntrance(models.Model):
    _name = "construction.entrance"
    _description = "Construction Entrance"
    _order = "building_id, sequence, name"

    name = fields.Char(string="Entrance Name", required=True)
    code = fields.Char(string="Entrance Code")
    sequence = fields.Integer(default=10)
    building_id = fields.Many2one(
        "construction.building",
        string="Building",
        required=True,
        ondelete="cascade",
    )
    active = fields.Boolean(default=True)
