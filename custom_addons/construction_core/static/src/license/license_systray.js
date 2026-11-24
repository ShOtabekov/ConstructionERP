/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LicenseSystray extends Component {
    static template = "construction_core.LicenseSystray";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ st: null });
        onWillStart(async () => {
            try {
                this.state.st = await this.orm.call("construction.license", "get_status", []);
            } catch {
                this.state.st = null;
            }
        });
    }

    get visible() {
        const st = this.state.st;
        if (!st) return false;
        if (st.state === "licensed") return st.days_left !== false && st.days_left <= 30;
        return true;
    }

    get label() {
        const st = this.state.st;
        if (st.state === "expired") return "Лицензия: нужен ключ";
        if (st.state === "trial") return `Пробный период: ${st.days_left} дн.`;
        return `Лицензия: осталось ${st.days_left} дн.`;
    }

    get cls() {
        return this.state.st.state === "expired" ? "bg-danger" : "bg-warning text-dark";
    }

    open() {
        this.action.doAction("construction_core.action_license_wizard");
    }
}

registry.category("systray").add("construction_core.license", { Component: LicenseSystray }, { sequence: 1 });

export class UpdateSystray extends Component {
    static template = "construction_core.UpdateSystray";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ info: {} });
        onWillStart(async () => {
            try {
                this.state.info = await this.orm.call("construction.update", "get_info", []);
            } catch {
                this.state.info = {};
            }
        });
    }

    open() {
        this.action.doAction("construction_core.action_update_wizard");
    }
}

registry.category("systray").add("construction_core.update", { Component: UpdateSystray }, { sequence: 2 });
