from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ConstructionApartment(models.Model):
    _name = "construction.apartment"
    _description = "Construction Apartment"
    _order = "floor_id, number"

    _apartment_number_unique = models.Constraint(
        "UNIQUE(floor_id, number)",
        "Apartment number must be unique within the same floor.",
    )

    name = fields.Char(
        string="Apartment",
        compute="_compute_name",
        store=True,
    )

    number = fields.Char(
        string="Apartment Number",
        required=True,
        index=True,
    )

    floor_id = fields.Many2one(
        "construction.floor",
        string="Floor",
        required=True,
        ondelete="restrict",
        index=True,
    )

    entrance_id = fields.Many2one(
        related="floor_id.entrance_id",
        store=True,
        string="Entrance",
    )

    building_id = fields.Many2one(
        related="floor_id.building_id",
        store=True,
        string="Building",
    )

    project_id = fields.Many2one(
        related="floor_id.project_id",
        store=True,
        string="Project",
    )

    floor_number = fields.Integer(
        related="floor_id.number",
        string="Floor Number",
    )

    layout_id = fields.Many2one(
        "construction.unit.layout",
        string="Layout",
        ondelete="set null",
        index=True,
        help="Position of the unit on the typical floor plan of the block.",
    )

    plan_html = fields.Html(
        string="Floor Plan",
        compute="_compute_plan_html",
        sanitize=False,
    )

    unit_type = fields.Selection(
        [
            ("apartment", "Apartment"),
            ("shop", "Shop"),
        ],
        string="Unit Type",
        default="apartment",
        required=True,
        index=True,
    )

    rooms = fields.Integer(
        string="Rooms",
        default=1,
        required=True,
    )

    area_total = fields.Float(
        string="Total Area (m2)",
        digits=(12, 2),
        required=True,
    )

    area_living = fields.Float(
        string="Living Area (m2)",
        digits=(12, 2),
    )

    # Existing company currency fields (TJS)
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.company_id.currency_id",
        string="Currency",
        store=True,
    )

    price_per_sqm = fields.Monetary(
        string="Price per m2 (TJS)",
        currency_field="currency_id",
    )

    total_price = fields.Monetary(
        string="Total Price (TJS)",
        compute="_compute_total_price",
        store=True,
        currency_field="currency_id",
    )

    # New USD fields
    currency_usd_id = fields.Many2one(
        "res.currency",
        string="USD Currency",
        default=lambda self: self.env.ref(
            "base.USD", raise_if_not_found=False
        ),
        readonly=True,
    )

    price_per_sqm_usd = fields.Monetary(
        string="Price per m2 (USD)",
        currency_field="currency_usd_id",
    )

    total_price_usd = fields.Monetary(
        string="Total Price (USD)",
        compute="_compute_total_price_usd",
        store=True,
        currency_field="currency_usd_id",
    )

    # Manual USD to TJS exchange rate for apartment pricing
    # One exchange rate per project (residential complex).
    usd_tjs_rate = fields.Float(
        related="project_id.usd_tjs_rate",
        store=True,
        readonly=True,
        string="USD/TJS Exchange Rate",
        digits=(12, 6),
    )

    price_per_sqm_tjs = fields.Monetary(
        string="Price per m2 (TJS, calculated)",
        compute="_compute_tjs_prices",
        store=True,
        currency_field="currency_id",
    )

    total_price_tjs = fields.Monetary(
        string="Total Price (TJS, calculated)",
        compute="_compute_tjs_prices",
        store=True,
        currency_field="currency_id",
    )

    state = fields.Selection(
        [
            ("free", "Free"),
            ("reserved", "Reserved"),
            ("sold", "Sold"),
            ("blocked", "Blocked"),
        ],
        string="Status",
        default="free",
        required=True,
        index=True,
        readonly=True,
        copy=False,
    )

    description = fields.Text(string="Description")

    active = fields.Boolean(default=True)

    @api.depends("number", "floor_id.number", "unit_type")
    def _compute_name(self):
        for record in self:
            floor_number = (
                record.floor_id.number
                if record.floor_id
                else ""
            )
            prefix = "Маг." if record.unit_type == "shop" else "Кв."
            record.name = (
                f"{prefix} {record.number}, {floor_number} этаж"
                if record.number
                else False
            )

    def _plan_data(self):
        """Floor plan image URL and marker position, or None."""
        self.ensure_one()
        layout = self.layout_id
        building = self.building_id
        if not (layout and building and building.floor_plan_image
                and (layout.plan_x or layout.plan_y)):
            return None
        return {
            "url": "/web/image/construction.building/%d/floor_plan_image"
                   % building.id,
            "x": layout.plan_x,
            "y": layout.plan_y,
            "unit_url": (
                "/web/image/construction.unit.layout/%d/plan_image" % layout.id
                if layout.plan_image else False
            ),
        }

    @api.depends(
        "layout_id.plan_x",
        "layout_id.plan_y",
        "layout_id.plan_image",
        "building_id.floor_plan_image",
    )
    def _compute_plan_html(self):
        for record in self:
            plan = record._plan_data() if record.id else None
            if not plan:
                record.plan_html = False
                continue
            unit = Markup("")
            if plan["unit_url"]:
                unit = Markup(
                    '<div style="margin-bottom:16px;">'
                    '<a href="%(unit_url)s" target="_blank">'
                    '<img src="%(unit_url)s" style="max-width:100%%;'
                    'max-height:520px;border:1px solid #dee2e6;'
                    'border-radius:8px;" alt="unit plan"/></a></div>'
                ) % plan
            record.plan_html = unit + Markup(
                '<div class="o_unit_plan" style="position:relative;'
                'display:inline-block;max-width:100%%;overflow:hidden;'
                'border-radius:8px;border:1px solid #dee2e6;">'
                '<a href="%(url)s" target="_blank">'
                '<img src="%(url)s" style="display:block;max-width:100%%;'
                'height:auto;" alt="plan"/></a>'
                '<span style="position:absolute;left:%(x).2f%%;top:%(y).2f%%;'
                'width:64px;height:64px;transform:translate(-50%%,-50%%);'
                'border:5px solid #e53935;border-radius:50%%;'
                'box-shadow:0 0 0 2000px rgba(0,0,0,.28);'
                'pointer-events:none;"></span></div>'
            ) % plan

    @api.depends("area_total", "price_per_sqm")
    def _compute_total_price(self):
        for record in self:
            record.total_price = (
                record.area_total * record.price_per_sqm
            )

    @api.depends("area_total", "price_per_sqm_usd")
    def _compute_total_price_usd(self):
        for record in self:
            record.total_price_usd = (
                record.area_total * record.price_per_sqm_usd
            )

    @api.depends(
        "area_total",
        "price_per_sqm_usd",
        "usd_tjs_rate",
    )
    def _compute_tjs_prices(self):
        for record in self:
            rate = record.usd_tjs_rate or 0.0

            if rate > 0:
                record.price_per_sqm_tjs = (
                    record.price_per_sqm_usd * rate
                )
                record.total_price_tjs = (
                    record.area_total
                    * record.price_per_sqm_usd
                    * rate
                )
            else:
                record.price_per_sqm_tjs = 0.0
                record.total_price_tjs = 0.0

    @api.constrains("usd_tjs_rate")
    def _check_usd_tjs_rate(self):
        for record in self:
            if record.usd_tjs_rate < 0:
                raise ValidationError(
                    "USD/TJS exchange rate cannot be negative."
                )

    @api.constrains("number", "floor_id")
    def _check_number(self):
        for record in self:
            if not record.number or not record.number.strip():
                raise ValidationError(
                    "Apartment number is required."
                )

    @api.constrains(
        "unit_type",
        "rooms",
        "area_total",
        "area_living",
        "price_per_sqm",
        "price_per_sqm_usd",
    )
    def _check_apartment_values(self):
        for record in self:
            if record.unit_type == "apartment" and record.rooms < 1:
                raise ValidationError(
                    "An apartment must have at least one room."
                )

            if record.area_total <= 0:
                raise ValidationError(
                    "Total area must be greater than zero."
                )

            if record.area_living < 0:
                raise ValidationError(
                    "Living area cannot be negative."
                )

            if record.area_living > record.area_total:
                raise ValidationError(
                    "Living area cannot exceed total area."
                )

            if record.price_per_sqm < 0:
                raise ValidationError(
                    "TJS price per square meter cannot be negative."
                )

            if record.price_per_sqm_usd < 0:
                raise ValidationError(
                    "USD price per square meter cannot be negative."
                )

    # ------------------------------------------------------------------
    # Status protection
    # ------------------------------------------------------------------
    # The apartment status is driven only by the sales workflow
    # (reservation / contract) and by explicit Block / Unblock buttons.
    # Direct writes of "state" (form, import, RPC) are rejected.

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "free") not in ("free", "blocked"):
                raise ValidationError(
                    _("A new apartment can only be Free or Blocked.")
                )
        return super().create(vals_list)

    def write(self, vals):
        if "state" in vals:
            raise ValidationError(
                _("Apartment status is changed only by reservations, "
                "contracts or the Block / Unblock buttons.")
            )
        return super().write(vals)

    def _set_state(self, state):
        """Internal workflow method (not callable via RPC)."""
        return super(ConstructionApartment, self.sudo()).write(
            {"state": state}
        )

    def _check_block_rights(self):
        user = self.env.user
        if user.has_group("base.group_system"):
            return
        group = self.env.ref(
            "construction_sales.group_sales_manager",
            raise_if_not_found=False,
        )
        if group and user.has_group("construction_sales.group_sales_manager"):
            return
        raise ValidationError(
            _("Only a sales supervisor can block or unblock apartments.")
        )

    def action_block(self):
        self._check_block_rights()
        for record in self:
            if record.state != "free":
                raise ValidationError(
                    _("Only a free apartment can be blocked.")
                )
            record._set_state("blocked")
        return True

    def action_unblock(self):
        self._check_block_rights()
        for record in self:
            if record.state != "blocked":
                raise ValidationError(
                    _("Only a blocked apartment can be unblocked.")
                )
            record._set_state("free")
        return True

    # ------------------------------------------------------------------
    # Chessboard (sales screen) API
    # ------------------------------------------------------------------
    # The chessboard widget calls chessboard_card() when a unit is
    # clicked. Each module (sales, finance) extends it with its own info
    # lines and action buttons. An action button calls the public method
    # named in "method" on construction.apartment and runs the returned
    # window action (or reloads the board when it returns True).

    def _chessboard_can_block(self):
        try:
            self._check_block_rights()
        except ValidationError:
            return False
        return True

    def chessboard_card(self):
        self.ensure_one()
        state_labels = dict(
            self._fields["state"]._description_selection(self.env)
        )
        card = {
            "id": self.id,
            "name": self.name,
            "number": self.number,
            "floor": self.floor_id.number,
            "building": self.building_id.name,
            "entrance": self.entrance_id.name,
            "project": self.project_id.name,
            "rooms": self.rooms,
            "area_total": self.area_total,
            "area_living": self.area_living,
            "price_per_sqm_usd": self.price_per_sqm_usd,
            "total_price_usd": self.total_price_usd,
            "total_price_tjs": self.total_price_tjs,
            "usd_tjs_rate": self.usd_tjs_rate,
            "unit_type": self.unit_type,
            "plan": self._plan_data(),
            "state": self.state,
            "state_label": state_labels.get(self.state, self.state),
            "info": [],
            "actions": [],
        }
        if self.state == "free" and self._chessboard_can_block():
            card["actions"].append({
                "method": "action_block",
                "label": _("Заблокировать"),
                "style": "secondary",
                "sequence": 80,
            })
        if self.state == "blocked" and self._chessboard_can_block():
            card["actions"].append({
                "method": "action_unblock",
                "label": _("Разблокировать"),
                "style": "secondary",
                "sequence": 80,
            })
        card["actions"].append({
            "method": "action_open_apartment_form",
            "label": _("Открыть карточку"),
            "style": "link",
            "sequence": 100,
        })
        return card

    def action_open_apartment_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "construction.apartment",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
