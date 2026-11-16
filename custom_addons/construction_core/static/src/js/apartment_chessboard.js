/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const STATUS = {
    free: "Свободна",
    reserved: "Бронь",
    sold: "Продана",
    blocked: "Заблокирована",
};

const ROOM_FILTERS = [
    { value: "", label: "Все" },
    { value: "1", label: "1К" },
    { value: "2", label: "2К" },
    { value: "3", label: "3К" },
    { value: "4", label: "4К+" },
];

const naturalCompare = (a, b) =>
    String(a).localeCompare(String(b), undefined, { numeric: true });

export class ApartmentChessboard extends Component {
    static template = "construction_core.ApartmentChessboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.statusList = Object.entries(STATUS).map(([value, label]) => ({ value, label }));
        this.roomFilters = ROOM_FILTERS;

        this.state = useState({
            loading: true,
            error: null,
            apartments: [],
            project: "",
            building: "",
            rooms: "",
            status: "",
            search: "",
            selectedId: null,
            card: null,
            planMode: "unit",
            cardLoading: false,
            busy: false,
        });

        onWillStart(() => this.loadApartments());
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------

    async loadApartments() {
        try {
            this.state.loading = true;
            this.state.error = null;
            this.state.apartments = await this.orm.searchRead(
                "construction.apartment",
                [["active", "=", true]],
                [
                    "number",
                    "rooms",
                    "unit_type",
                    "area_total",
                    "total_price_usd",
                    "state",
                    "floor_id",
                    "floor_number",
                    "entrance_id",
                    "building_id",
                    "project_id",
                ],
            );
        } catch (error) {
            console.error("Apartment chessboard loading error:", error);
            this.state.error =
                "Не удалось загрузить квартиры. Проверьте права доступа и журнал Odoo.";
        } finally {
            this.state.loading = false;
        }
    }

    async loadCard(id) {
        this.state.cardLoading = true;
        try {
            this.state.card = await this.orm.call(
                "construction.apartment",
                "chessboard_card",
                [[id]],
            );
            this.state.card.actions.sort((a, b) => (a.sequence || 50) - (b.sequence || 50));
        } finally {
            this.state.cardLoading = false;
        }
    }

    // ------------------------------------------------------------------
    // Filters
    // ------------------------------------------------------------------

    uniqueOptions(field, apartments = this.state.apartments) {
        const values = new Map();
        for (const apartment of apartments) {
            const value = apartment[field];
            if (value) {
                values.set(value[0], { id: value[0], name: value[1] });
            }
        }
        return [...values.values()].sort((a, b) => naturalCompare(a.name, b.name));
    }

    get projects() {
        return this.uniqueOptions("project_id");
    }

    get projectApartments() {
        const project = Number(this.state.project);
        return project
            ? this.state.apartments.filter((a) => a.project_id?.[0] === project)
            : this.state.apartments;
    }

    get buildings() {
        return this.uniqueOptions("building_id", this.projectApartments);
    }

    get scopeApartments() {
        const building = Number(this.state.building);
        return building
            ? this.projectApartments.filter((a) => a.building_id?.[0] === building)
            : this.projectApartments;
    }

    get hasHighlightFilter() {
        return Boolean(this.state.rooms || this.state.status || this.state.search.trim());
    }

    matches(apartment) {
        const { rooms, status } = this.state;
        const search = this.state.search.trim().toLowerCase();
        if (rooms) {
            const wanted = Number(rooms);
            if (wanted >= 4 ? apartment.rooms < 4 : apartment.rooms !== wanted) {
                return false;
            }
        }
        if (status && apartment.state !== status) {
            return false;
        }
        if (search && !String(apartment.number || "").toLowerCase().includes(search)) {
            return false;
        }
        return true;
    }

    get matchCount() {
        return this.scopeApartments.filter((a) => this.matches(a)).length;
    }

    get stats() {
        const result = { total: 0, free: 0, reserved: 0, sold: 0, blocked: 0 };
        for (const apartment of this.scopeApartments) {
            result.total += 1;
            result[apartment.state] = (result[apartment.state] || 0) + 1;
        }
        return result;
    }

    /** Blocks -> floors (top floor first) -> units. */
    get blocks() {
        const blocks = new Map();
        for (const apartment of this.scopeApartments) {
            const buildingId = apartment.building_id?.[0] || 0;
            if (!blocks.has(buildingId)) {
                blocks.set(buildingId, {
                    id: buildingId,
                    name: apartment.building_id?.[1] || "Без корпуса",
                    floors: new Map(),
                    total: 0,
                    free: 0,
                });
            }
            const block = blocks.get(buildingId);
            block.total += 1;
            if (apartment.state === "free") {
                block.free += 1;
            }
            const floorKey = apartment.floor_id?.[0] || 0;
            if (!block.floors.has(floorKey)) {
                block.floors.set(floorKey, {
                    id: floorKey,
                    number: apartment.floor_number,
                    entrance: apartment.entrance_id?.[1] || "",
                    units: [],
                });
            }
            block.floors.get(floorKey).units.push(apartment);
        }

        return [...blocks.values()]
            .sort((a, b) => naturalCompare(a.name, b.name))
            .map((block) => ({
                ...block,
                floors: [...block.floors.values()]
                    .sort((a, b) => b.number - a.number)
                    .map((floor) => ({
                        ...floor,
                        units: floor.units.sort((a, b) => naturalCompare(a.number, b.number)),
                    })),
            }));
    }

    setValue(name, value) {
        this.state[name] = value;
    }

    statusChipClass(value) {
        return `o_state_${value}` + (this.state.status === value ? " active" : "");
    }

    setFilter(name, value) {
        this.state[name] = this.state[name] === value ? "" : value;
    }

    toggleBuilding(id) {
        this.setFilter("building", String(id));
    }

    onProjectChange(event) {
        this.state.project = event.target.value;
        this.state.building = "";
    }

    onSearchInput(event) {
        this.state.search = event.target.value;
    }

    clearFilters() {
        Object.assign(this.state, {
            project: "",
            building: "",
            rooms: "",
            status: "",
            search: "",
        });
    }

    // ------------------------------------------------------------------
    // Units and card
    // ------------------------------------------------------------------

    unitClass(apartment) {
        const classes = [`o_unit o_state_${apartment.state}`];
        if (this.hasHighlightFilter && !this.matches(apartment)) {
            classes.push("o_dimmed");
        }
        if (apartment.id === this.state.selectedId) {
            classes.push("o_selected");
        }
        return classes.join(" ");
    }

    unitTitle(apartment) {
        const price = (apartment.total_price_usd || 0).toLocaleString("ru-RU");
        const kind = apartment.unit_type === "shop"
            ? `Маг. ${apartment.number}`
            : `Кв. ${apartment.number} · ${apartment.rooms}К`;
        return `${kind} · ${apartment.area_total} м² · $${price} · ${STATUS[apartment.state] || apartment.state}`;
    }

    unitMeta(apartment) {
        return apartment.unit_type === "shop"
            ? `Маг · ${apartment.area_total}`
            : `${apartment.rooms}К · ${apartment.area_total}`;
    }

    statusLabel(state) {
        return STATUS[state] || state;
    }

    money(value, currency = "$") {
        const formatted = Number(value || 0).toLocaleString("ru-RU", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2,
        });
        return currency === "$" ? `$ ${formatted}` : `${formatted} ${currency}`;
    }

    async selectUnit(apartment) {
        if (this.state.selectedId === apartment.id) {
            this.closeCard();
            return;
        }
        this.state.selectedId = apartment.id;
        this.state.card = null;
        await this.loadCard(apartment.id);
    }

    closeCard() {
        this.state.selectedId = null;
        this.state.card = null;
    }

    async runAction(method) {
        const id = this.state.selectedId;
        if (!id || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const result = await this.orm.call("construction.apartment", method, [[id]]);
            if (result && typeof result === "object" && result.type) {
                await this.action.doAction(result);
                return;
            }
            await this.loadApartments();
            await this.loadCard(id);
        } finally {
            this.state.busy = false;
        }
    }

    actionClass(action) {
        return {
            primary: "btn btn-primary",
            success: "btn btn-success",
            secondary: "btn btn-outline-secondary",
            link: "btn btn-link",
        }[action.style] || "btn btn-outline-secondary";
    }
}

registry.category("actions").add(
    "construction_apartment_chessboard",
    ApartmentChessboard
);
