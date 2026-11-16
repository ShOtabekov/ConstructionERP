/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ApartmentChessboard extends Component {
    static template = "construction_core.ApartmentChessboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            error: null,
            mode: "chessboard",
            apartments: [],
            project: "",
            building: "",
            entrance: "",
        });

        onWillStart(() => this.loadApartments());
    }

    async loadApartments() {
        try {
            this.state.loading = true;
            this.state.error = null;

            const records = await this.orm.searchRead(
                "construction.apartment",
                [["active", "=", true]],
                [
                    "number",
                    "rooms",
                    "area_total",
                    "total_price_usd",
                    "total_price_tjs",
                    "state",
                    "floor_id",
                    "entrance_id",
                    "building_id",
                    "project_id",
                ],
                { order: "floor_id, number" }
            );

            this.state.apartments = records;
        } catch (error) {
            console.error("Apartment chessboard loading error:", error);
            this.state.error = "Не удалось загрузить квартиры. Проверьте права доступа и журнал Odoo.";
        } finally {
            this.state.loading = false;
        }
    }

    get projects() {
        return this.uniqueOptions("project_id");
    }

    get buildings() {
        return this.uniqueOptions("building_id").filter(
            (item) => !this.state.project ||
                this.state.apartments.some(
                    (a) => a.building_id?.[0] === item.id &&
                        a.project_id?.[0] === Number(this.state.project)
                )
        );
    }

    get entrances() {
        return this.uniqueOptions("entrance_id").filter(
            (item) => !this.state.building ||
                this.state.apartments.some(
                    (a) => a.entrance_id?.[0] === item.id &&
                        a.building_id?.[0] === Number(this.state.building)
                )
        );
    }

    uniqueOptions(field) {
        const values = new Map();

        for (const apartment of this.state.apartments) {
            const value = apartment[field];
            if (value) {
                values.set(value[0], {
                    id: value[0],
                    name: value[1],
                });
            }
        }

        return [...values.values()].sort(
            (a, b) => a.name.localeCompare(b.name)
        );
    }

    get filteredApartments() {
        return this.state.apartments.filter((a) => {
            if (this.state.project &&
                a.project_id?.[0] !== Number(this.state.project)) return false;

            if (this.state.building &&
                a.building_id?.[0] !== Number(this.state.building)) return false;

            if (this.state.entrance &&
                a.entrance_id?.[0] !== Number(this.state.entrance)) return false;

            return true;
        });
    }

    get floors() {
        const groups = new Map();

        for (const apartment of this.filteredApartments) {
            const floor = apartment.floor_id;
            if (!floor) continue;

            if (!groups.has(floor[0])) {
                groups.set(floor[0], {
                    id: floor[0],
                    name: floor[1],
                    apartments: [],
                    entrance: apartment.entrance_id?.[1] || "",
                    building: apartment.building_id?.[1] || "",
                });
            }

            groups.get(floor[0]).apartments.push(apartment);
        }

        return [...groups.values()].sort((a, b) =>
            a.name.localeCompare(b.name, undefined, { numeric: true })
        );
    }

    get entrancesGroups() {
        const groups = new Map();

        for (const floor of this.floors) {
            const key = floor.entrance || "Без подъезда";

            if (!groups.has(key)) {
                groups.set(key, {
                    name: key,
                    floors: [],
                });
            }

            groups.get(key).floors.push(floor);
        }

        return [...groups.values()];
    }

    setMode(mode) {
        this.state.mode = mode;
    }

    onProjectChange(event) {
        this.state.project = event.target.value;
        this.state.building = "";
        this.state.entrance = "";
    }

    onBuildingChange(event) {
        this.state.building = event.target.value;
        this.state.entrance = "";
    }

    onEntranceChange(event) {
        this.state.entrance = event.target.value;
    }

    clearFilters() {
        this.state.project = "";
        this.state.building = "";
        this.state.entrance = "";
    }

    statusLabel(state) {
        return {
            free: "Свободна",
            reserved: "Бронь",
            sold: "Продана",
            blocked: "Блок",
        }[state] || state;
    }

    async openApartment(id) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Квартира",
            res_model: "construction.apartment",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add(
    "construction_apartment_chessboard",
    ApartmentChessboard
);
