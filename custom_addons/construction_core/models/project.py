from odoo import api, models, fields
from odoo.exceptions import ValidationError


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

    usd_tjs_rate = fields.Float(
        string="USD/TJS Exchange Rate",
        digits=(12, 6),
        help="One rate for the whole complex: TJS for 1 USD. "
             "Used to show TJS prices. Reservations and contracts "
             "fix the rate at the moment of confirmation.",
    )

    rate_date = fields.Date(
        string="Rate Date",
        help="Date the exchange rate was last updated.",
    )

    @api.constrains("usd_tjs_rate")
    def _check_usd_tjs_rate(self):
        for project in self:
            if project.usd_tjs_rate < 0:
                raise ValidationError(
                    "USD/TJS exchange rate cannot be negative."
                )

    def write(self, vals):
        if "usd_tjs_rate" in vals and "rate_date" not in vals:
            vals["rate_date"] = fields.Date.context_today(self)
        return super().write(vals)

    _code_company_unique = models.Constraint(
        "UNIQUE(code, company_id)",
        "Project code must be unique per company!",
    )

