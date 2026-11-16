from odoo import models, fields, api


class ConstructionFloor(models.Model):
    _name = "construction.floor"
    _description = "Construction Floor"
    _order = "entrance_id, number"

    name = fields.Char(
        string="Floor Name",
        compute="_compute_name",
        store=True,
    )
    number = fields.Integer(string="Floor Number", required=True)

    entrance_id = fields.Many2one(
        "construction.entrance",
        string="Entrance",
        required=True,
        ondelete="cascade",
    )

    building_id = fields.Many2one(
        related="entrance_id.building_id",
        store=True,
        string="Building",
    )

    project_id = fields.Many2one(
        related="building_id.project_id",
        store=True,
        string="Project",
    )

    @api.depends("number")
    def _compute_name(self):
        for record in self:
            record.name = f"Floor {record.number}"
