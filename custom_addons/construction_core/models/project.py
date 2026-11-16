from odoo import models, fields


class ConstructionProject(models.Model):
    _name = "construction.project"
    _description = "Construction Project"
    _order = "name"

    name = fields.Char(
        string="Project Name",
        required=True
    )

    code = fields.Char(
        string="Project Code",
        required=True,
        copy=False
    )

    location = fields.Char(
        string="Location"
    )

    description = fields.Text(
        string="Description"
    )

    start_date = fields.Date(
        string="Start Date"
    )

    end_date = fields.Date(
        string="End Date"
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True
    )

    _code_company_unique = models.Constraint(
        "UNIQUE(code, company_id)",
        "Project code must be unique per company!",
    )

