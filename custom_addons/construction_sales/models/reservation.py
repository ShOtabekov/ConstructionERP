import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


class ConstructionReservation(models.Model):
    _name = "construction.reservation"
    _description = "Construction Apartment Reservation"
    _order = "date_start desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Reservation Number",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        tracking=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Buyer",
        required=True,
        index=True,
        tracking=True,
        ondelete="restrict",
    )

    apartment_id = fields.Many2one(
        "construction.apartment",
        string="Apartment",
        required=True,
        index=True,
        tracking=True,
        ondelete="restrict",
    )

    project_id = fields.Many2one(
        related="apartment_id.project_id",
        string="Project",
        store=True,
        readonly=True,
    )

    building_id = fields.Many2one(
        related="apartment_id.building_id",
        string="Building",
        store=True,
        readonly=True,
    )

    date_start = fields.Datetime(
        string="Reservation Start",
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )

    date_end = fields.Datetime(
        string="Reservation Expiration",
        required=True,
        tracking=True,
    )

    price_usd = fields.Monetary(
        string="Reserved Price (USD)",
        currency_field="currency_usd_id",
        readonly=True,
        copy=False,
        tracking=True,
    )

    currency_usd_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.ref(
            "base.USD", raise_if_not_found=False
        ),
        readonly=True,
    )

    exchange_rate = fields.Float(
        string="USD/TJS Rate",
        digits=(12, 6),
        readonly=True,
        copy=False,
        tracking=True,
    )

    price_tjs = fields.Monetary(
        string="Reserved Price (TJS)",
        currency_field="currency_tjs_id",
        readonly=True,
        copy=False,
    )

    currency_tjs_id = fields.Many2one(
        "res.currency",
        related="apartment_id.currency_id",
        readonly=True,
    )

    user_id = fields.Many2one(
        "res.users",
        string="Responsible Manager",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("reserved", "Reserved"),
            ("converted", "Converted to Contract"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )

    contract_id = fields.Many2one(
        "construction.contract",
        string="Sales Contract",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )

    notes = fields.Text(string="Notes")

    _date_range_check = models.Constraint(
        "CHECK(date_end > date_start)",
        "Reservation expiration must be later than its start.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise UserError(
                    _("Reservations must be created in Draft status.")
                )

            if vals.get("contract_id"):
                raise UserError(
                    _("A contract cannot be linked during reservation creation.")
                )

            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code(
                        "construction.reservation"
                    ) or _("New")
                )

        return super().create(vals_list)

    def write(self, vals):
        if "state" in vals:
            raise UserError(
                _("Use reservation action buttons to change status.")
            )

        if "contract_id" in vals:
            raise UserError(
                _("Contract links are managed by the contract workflow.")
            )

        protected_fields = {
            "partner_id",
            "apartment_id",
            "date_start",
            "date_end",
            "price_usd",
            "exchange_rate",
            "price_tjs",
            "currency_usd_id",
            "user_id",
        }

        for record in self:
            if record.state != "draft" and protected_fields.intersection(vals):
                raise UserError(
                    _("Confirmed reservation details cannot be modified.")
                )

        return super().write(vals)

    def _write_workflow(self, vals):
        """Internal workflow write; do not expose through context flags."""
        return super(ConstructionReservation, self).write(vals)

    def unlink(self):
        for record in self:
            if record.state != "draft":
                raise UserError(
                    _("Only draft reservations can be deleted.")
                )

        return super().unlink()

    def _lock_apartment(self):
        self.ensure_one()

        self.env.cr.execute(
            """
            SELECT id
            FROM construction_apartment
            WHERE id = %s
            FOR UPDATE
            """,
            [self.apartment_id.id],
        )

        if not self.env.cr.fetchone():
            raise UserError(_("Apartment does not exist."))

        self.apartment_id.invalidate_recordset()

    def _has_active_contract(self, apartment):
        return self.env["construction.contract"].sudo().search_count([
            ("apartment_id", "=", apartment.id),
            ("state", "=", "confirmed"),
        ])

    def _has_other_active_reservation(self, apartment, exclude_id=None, now=None):
        domain = [
            ("apartment_id", "=", apartment.id),
            ("state", "=", "reserved"),
        ]

        if exclude_id:
            domain.append(("id", "!=", exclude_id))

        if now:
            domain.append(("date_end", ">", now))

        return self.sudo().search_count(domain)

    def _expire_apartment_reservations(self, apartment, now=None):
        """Expire overdue reservations while the apartment row is locked."""
        now = now or fields.Datetime.now()

        expired = self.sudo().search([
            ("apartment_id", "=", apartment.id),
            ("state", "=", "reserved"),
            ("date_end", "<=", now),
        ])

        for reservation in expired:
            reservation.invalidate_recordset()
            if (
                reservation.state == "reserved"
                and reservation.date_end <= now
            ):
                reservation._write_workflow({"state": "expired"})

        self._release_apartment_if_available(apartment)
        apartment.invalidate_recordset()
        return True

    def _release_apartment_if_available(self, apartment, exclude_id=None):
        apartment.invalidate_recordset()

        # Never release blocked or sold apartments automatically.
        if apartment.state in ("blocked", "sold"):
            return False

        if self._has_active_contract(apartment):
            return False

        if self._has_other_active_reservation(
            apartment,
            exclude_id=exclude_id,
            now=fields.Datetime.now(),
        ):
            return False

        apartment._set_state("free")
        return True

    def _check_sales_user(self):
        if (
            not self.env.user.has_group("base.group_system")
            and not self.env.user.has_group(
                "construction_sales.group_sales_user"
            )
        ):
            raise UserError(
                _("You do not have permission to manage reservations.")
            )


    def action_confirm(self):
        self._check_sales_user()
        for record in self:
            if record.state != "draft":
                raise UserError(
                    _("Only draft reservations can be confirmed.")
                )

            if record.date_end <= fields.Datetime.now():
                raise UserError(
                    _("Reservation expiration must be in the future.")
                )

            record._lock_apartment()
            apartment = record.apartment_id

            # Clear overdue reservations before checking availability.
            record._expire_apartment_reservations(apartment)
            apartment.invalidate_recordset()

            if apartment.state != "free":
                raise UserError(
                    _("This apartment is not available for reservation.")
                )

            if self._has_other_active_reservation(
                apartment,
                now=fields.Datetime.now(),
            ):
                raise UserError(
                    _("This apartment already has an active reservation.")
                )

            if record._has_active_contract(apartment):
                raise UserError(
                    _("This apartment already has a confirmed contract.")
                )

            if apartment.total_price_usd <= 0:
                raise UserError(
                    _("Apartment USD price must be greater than zero.")
                )

            if apartment.usd_tjs_rate <= 0:
                raise UserError(
                    _("A valid USD/TJS exchange rate is required.")
                )

            record._write_workflow({
                "price_usd": apartment.total_price_usd,
                "exchange_rate": apartment.usd_tjs_rate,
                "price_tjs": (
                    apartment.total_price_usd * apartment.usd_tjs_rate
                ),
                "state": "reserved",
            })

            apartment._set_state("reserved")

        return True

    def action_cancel(self):
        self._check_sales_user()
        for record in self:
            if record.state not in ("draft", "reserved"):
                raise UserError(
                    _("Only draft or active reservations can be cancelled.")
                )

            if record.state == "reserved":
                record._lock_apartment()

                if record._has_active_contract(record.apartment_id):
                    raise UserError(
                        _("Cannot cancel a reservation linked to a confirmed contract.")
                    )

                record._write_workflow({"state": "cancelled"})

                record._release_apartment_if_available(
                    record.apartment_id,
                    exclude_id=record.id,
                )
            else:
                record._write_workflow({"state": "cancelled"})

        return True

    def action_create_contract(self):
        self.ensure_one()
        self._check_sales_user()

        if self.state != "reserved":
            raise UserError(
                _("Only active reservations can be converted into contracts.")
            )

        if self.date_end <= fields.Datetime.now():
            raise UserError(_("This reservation has expired."))

        Contract = self.env["construction.contract"]

        # Reopen an existing contract instead of creating a duplicate.
        contract = Contract.search(
            [("reservation_id", "=", self.id)],
            limit=1,
        )

        if not contract:
            contract = Contract.create({
                "reservation_id": self.id,
                "partner_id": self.partner_id.id,
                "apartment_id": self.apartment_id.id,
                "price_usd": self.price_usd,
                "exchange_rate": self.exchange_rate,
                "price_tjs": self.price_tjs,
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Sales Contract"),
            "res_model": "construction.contract",
            "view_mode": "form",
            "res_id": contract.id,
            "target": "current",
        }

    @api.model
    def _cron_expire_reservations(self):
        now = fields.Datetime.now()

        expired_records = self.sudo().search([
            ("state", "=", "reserved"),
            ("date_end", "<=", now),
        ])

        for record in expired_records:
            try:
                with self.env.cr.savepoint():
                    record._lock_apartment()
                    record.invalidate_recordset()

                    if record.state != "reserved":
                        continue

                    if record.date_end > now:
                        continue

                    record._write_workflow({"state": "expired"})

                    record._release_apartment_if_available(
                        record.apartment_id,
                        exclude_id=record.id,
                    )

            except Exception:
                _logger.exception(
                    "Failed to expire construction reservation ID %s",
                    record.id,
                )

        return True
