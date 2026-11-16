from odoo import models, fields


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
