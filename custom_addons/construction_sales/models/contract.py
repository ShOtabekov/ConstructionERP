from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConstructionContract(models.Model):
    _name = "construction.contract"
    _description = "Construction Sales Contract"
    _order = "contract_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Contract Number",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        tracking=True,
    )

    reservation_id = fields.Many2one(
        "construction.reservation",
        string="Reservation",
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
        tracking=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Buyer",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )

    apartment_id = fields.Many2one(
        "construction.apartment",
        string="Apartment",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
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

    contract_date = fields.Date(
        string="Contract Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )

    currency_usd_id = fields.Many2one(
        "res.currency",
        string="USD Currency",
        default=lambda self: self.env.ref(
            "base.USD", raise_if_not_found=False
        ),
        readonly=True,
    )

    currency_tjs_id = fields.Many2one(
        "res.currency",
        related="apartment_id.currency_id",
        string="TJS Currency",
        readonly=True,
    )

    price_usd = fields.Monetary(
        string="Contract Price (USD)",
        currency_field="currency_usd_id",
        readonly=True,
        copy=False,
        tracking=True,
    )

    exchange_rate = fields.Float(
        string="USD/TJS Exchange Rate",
        digits=(12, 6),
        readonly=True,
        copy=False,
        tracking=True,
    )

    price_tjs = fields.Monetary(
        string="Contract Price (TJS)",
        currency_field="currency_tjs_id",
        readonly=True,
        copy=False,
        tracking=True,
    )

    user_id = fields.Many2one(
        "res.users",
        string="Responsible Manager",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )

    contract_file = fields.Binary(
        string="Signed Contract",
        attachment=True,
    )

    contract_filename = fields.Char(string="File Name")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )

    notes = fields.Text(string="Notes")

    _reservation_unique = models.Constraint(
        "UNIQUE(reservation_id)",
        "A reservation can only be converted into one contract.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise UserError(
                    _("Contracts must be created in Draft status.")
                )

            if not vals.get("reservation_id") and vals.get("apartment_id"):
                apartment = self.env[
                    "construction.apartment"
                ].browse(vals["apartment_id"]).exists()

                if not apartment:
                    raise ValidationError(_("Apartment does not exist."))

                if apartment.state != "free":
                    raise UserError(
                        _("A direct contract can only be created for a free apartment. "
                          "For reserved apartments, create the contract from the active reservation.")
                    )

            if vals.get("reservation_id"):
                reservation = self.env[
                    "construction.reservation"
                ].browse(vals["reservation_id"]).exists()

                if not reservation:
                    raise ValidationError(_("Reservation does not exist."))

                if reservation.state != "reserved":
                    raise UserError(
                        _("Only active reservations can be linked to a contract.")
                    )

                if vals.get("apartment_id") and (
                    reservation.apartment_id.id != vals["apartment_id"]
                ):
                    raise ValidationError(
                        _("Reservation and contract apartments do not match.")
                    )

                if vals.get("partner_id") and (
                    reservation.partner_id.id != vals["partner_id"]
                ):
                    raise ValidationError(
                        _("Reservation and contract buyers do not match.")
                    )

            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code(
                        "construction.contract"
                    ) or _("New")
                )

        return super().create(vals_list)

    def write(self, vals):
        # Draft apartment reassignment validation
        if "apartment_id" in vals:
            new_apartment_id = vals.get("apartment_id")
            if not new_apartment_id:
                raise ValidationError(_("A contract must have an apartment."))

            apartment = self.env["construction.apartment"].browse(
                new_apartment_id
            ).exists()

            if not apartment:
                raise ValidationError(_("Apartment does not exist."))

            for contract in self:
                if contract.state != "draft":
                    raise UserError(
                        _("The apartment cannot be changed after contract confirmation.")
                    )

                if contract.reservation_id:
                    reservation = contract.reservation_id
                    if reservation.state != "reserved":
                        raise UserError(
                            _("The reservation must be active to change the contract apartment.")
                        )
                    if reservation.apartment_id.id != apartment.id:
                        raise ValidationError(
                            _("The contract apartment must match its reservation apartment.")
                        )
                    if apartment.state != "reserved":
                        raise UserError(
                            _("The reserved apartment is not in the expected reserved state.")
                        )
                elif apartment.state != "free":
                    raise UserError(
                        _("A direct draft contract can only be assigned to a free apartment.")
                    )

        if "state" in vals:
            raise UserError(
                _("Use contract action buttons to change status.")
            )

        if "reservation_id" in vals:
            raise UserError(
                _("Reservation links cannot be changed after creation.")
            )

        protected_fields = {
            "partner_id",
            "apartment_id",
            "contract_date",
            "price_usd",
            "exchange_rate",
            "price_tjs",
            "currency_usd_id",
            "user_id",
        }

        for record in self:
            if record.state != "draft" and protected_fields.intersection(vals):
                raise UserError(
                    _("Confirmed contract terms cannot be modified.")
                )

        return super().write(vals)

    def _write_workflow(self, vals):
        """Internal workflow write; not controlled by context flags."""
        return super(ConstructionContract, self).write(vals)

    def unlink(self):
        for record in self:
            if record.state != "draft":
                raise UserError(
                    _("Only draft contracts can be deleted.")
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
        return self.sudo().search_count([
            ("apartment_id", "=", apartment.id),
            ("state", "=", "confirmed"),
        ])

    def _check_sales_user(self):
        if (
            not self.env.user.has_group("base.group_system")
            and not self.env.user.has_group(
                "construction_sales.group_sales_user"
            )
        ):
            raise UserError(
                _("You do not have permission to manage contracts.")
            )

    def _check_sales_supervisor(self):
        if (
            not self.env.user.has_group("base.group_system")
            and not self.env.user.has_group(
                "construction_sales.group_sales_manager"
            )
        ):
            raise UserError(
                _("Only a sales supervisor can cancel contracts.")
            )


    def action_confirm(self):
        self._check_sales_user()
        for record in self:
            if record.state != "draft":
                raise UserError(
                    _("Only draft contracts can be confirmed.")
                )

            record._lock_apartment()

            apartment = record.apartment_id

            # Expire stale reservations before evaluating apartment status.
            self.env["construction.reservation"]._expire_apartment_reservations(
                apartment
            )
            apartment.invalidate_recordset()

            reservation = record.reservation_id

            if record._has_active_contract(apartment):
                raise UserError(
                    _("This apartment already has a confirmed contract.")
                )

            if reservation:
                reservation.invalidate_recordset()

                if reservation.state != "reserved":
                    raise UserError(
                        _("The linked reservation is not active.")
                    )

                if reservation.date_end <= fields.Datetime.now():
                    raise UserError(_("The reservation has expired."))

                if reservation.apartment_id != apartment:
                    raise ValidationError(
                        _("Reservation and contract apartments do not match.")
                    )

                if reservation.partner_id != record.partner_id:
                    raise ValidationError(
                        _("Reservation and contract buyers do not match.")
                    )

                if apartment.state != "reserved":
                    raise UserError(
                        _("Apartment reservation status is inconsistent.")
                    )

                price_usd = reservation.price_usd
                exchange_rate = reservation.exchange_rate
                price_tjs = reservation.price_tjs

            else:
                if apartment.state != "free":
                    raise UserError(
                        _("Direct contract requires a free apartment.")
                    )

                price_usd = apartment.total_price_usd
                exchange_rate = apartment.usd_tjs_rate
                price_tjs = price_usd * exchange_rate

            # A price / rate negotiated on the draft contract (sale wizard)
            # takes precedence over the price list and the reservation.
            if record.price_usd > 0 or record.exchange_rate > 0:
                if record.price_usd > 0:
                    price_usd = record.price_usd
                if record.exchange_rate > 0:
                    exchange_rate = record.exchange_rate
                price_tjs = price_usd * exchange_rate

            if price_usd <= 0:
                raise UserError(
                    _("Apartment USD price must be greater than zero.")
                )

            if exchange_rate <= 0:
                raise UserError(
                    _("A valid USD/TJS exchange rate is required.")
                )

            record._write_workflow({
                "price_usd": price_usd,
                "exchange_rate": exchange_rate,
                "price_tjs": price_tjs,
                "state": "confirmed",
            })

            apartment._set_state("sold")

            if reservation:
                reservation._write_workflow({
                    "state": "converted",
                    "contract_id": record.id,
                })

        return True

    def action_cancel(self):
        self._check_sales_supervisor()
        for record in self:
            if record.state != "confirmed":
                raise UserError(
                    _("Only confirmed contracts can be cancelled.")
                )

            record._lock_apartment()

            apartment = record.apartment_id

            active_contracts = self.sudo().search_count([
                ("apartment_id", "=", apartment.id),
                ("state", "=", "confirmed"),
                ("id", "!=", record.id),
            ])

            if active_contracts:
                raise UserError(
                    _("Another confirmed contract exists for this apartment.")
                )

            if record.reservation_id:
                record.reservation_id.invalidate_recordset()

                if record.reservation_id.state == "converted":
                    record.reservation_id._write_workflow({
                        "state": "cancelled",
                    })

            record._write_workflow({
                "state": "cancelled",
            })

            active_reservations = self.env[
                "construction.reservation"
            ].sudo().search_count([
                ("apartment_id", "=", apartment.id),
                ("state", "=", "reserved"),
                ("date_end", ">", fields.Datetime.now()),
            ])

            apartment.invalidate_recordset()

            if apartment.state == "blocked":
                # Preserve an explicitly blocked apartment.
                pass
            elif active_reservations:
                apartment._set_state("reserved")
            else:
                apartment._set_state("free")

        return True
