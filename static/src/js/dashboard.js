/** @odoo-module **/
/**
 * PARCHE PARA dashboard.js (centro_canino_dashboard)
 *
 * Añade el botón "🎟️ Bonos" al panel de control.
 * Copia este método openBonos dentro de la clase CentroCaninoDashboard,
 * y añade el binding en setup().
 *
 * ─────────────────────────────────────────────────────────────────────
 * CAMBIOS EN setup():
 *
 *   this.openBonos = this.openBonos.bind(this);
 *
 * ─────────────────────────────────────────────────────────────────────
 * NUEVO MÉTODO (añadir junto a openOcupaciones):
 */

// async openBonos() {
//     await this.actionService.doAction(
//         "centro_canino_tumburu.action_bonos_activos"
//     );
// }

/**
 * ─────────────────────────────────────────────────────────────────────
 * CAMBIOS EN LA PLANTILLA XML del dashboard (Dashboard.xml):
 *
 * Dentro del bloque de botones/tarjetas de estadísticas, añadir:
 *
 *   <button class="btn btn-outline-warning btn-lg"
 *           t-on-click="() => openBonos()">
 *       🎟️ Bonos
 *       <span class="badge bg-warning text-dark ms-1"
 *             t-if="state.data and state.data.bonos_activos">
 *           <t t-esc="state.data.bonos_activos"/>
 *       </span>
 *   </button>
 *
 * ─────────────────────────────────────────────────────────────────────
 * CAMBIOS EN el controlador Python del dashboard
 * (CentroCaninoDashboardController / centro_canino.dashboard):
 *
 * En get_dashboard_data(), añadir al dict de retorno:
 *
 *   'bonos_activos': self.env['sale.order.line'].search_count([
 *       ('is_voucher', '=', True),
 *       ('sesiones_restantes', '>', 0),
 *   ]),
 *
 * ─────────────────────────────────────────────────────────────────────
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

function formatCurrency(val) {
    return new Intl.NumberFormat("es-ES", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: 0,
    }).format(val);
}

const ESTADO_LABELS = {
    "1_reservas": "Reserva",
    "2_in":       "In",
    "3_salidas":  "Salida",
    "4_cancelada":"Cancelada",
};
const ESTADO_CLASS = {
    "1_reservas": "badge-reserva",
    "2_in":       "badge-in",
    "3_salidas":  "badge-salida",
    "4_cancelada":"badge-cancelada",
};

class CentroCaninoDashboard extends Component {
    static template = "centro_canino_dashboard.Dashboard";

    setup() {
        this.rpc           = useService("rpc");
        this.orm           = useService("orm");
        this.actionService = useService("action");

        this.state = useState({
            loading:       true,
            periodo:       "30",
            filtroSubtipo: null,
            data:          null,
            error:         null,
        });

        this.openOcupaciones  = this.openOcupaciones.bind(this);
        this.openBonos        = this.openBonos.bind(this);   // ← NUEVO
        this.onPeriodoChange  = this.onPeriodoChange.bind(this);
        this.onSubtipoChange  = this.onSubtipoChange.bind(this);
        this.onRefresh        = this.onRefresh.bind(this);

        onWillStart(() => this._loadData());
    }

    async _loadData() {
        this.state.loading = true;
        this.state.error   = null;
        try {
            const data = await this.rpc("/centro_canino/dashboard/data", {
                periodo:        this.state.periodo,
                filtro_subtipo: this.state.filtroSubtipo,
            });
            this.state.data = this._processData(data);
        } catch (e) {
            console.error("Dashboard error:", e);
            this.state.error = e.message || "Error desconocido";
        } finally {
            this.state.loading = false;
        }
    }

    _processData(data) {
        if (!data) return data;
        data.periodo.ingresos_fmt = formatCurrency(data.periodo.ingresos);
        data.ultimas = (data.ultimas || []).map(o => ({
            ...o,
            estado_label: ESTADO_LABELS[o.estado] || o.estado,
            estado_class: ESTADO_CLASS[o.estado]  || "badge-reserva",
        }));
        data.grafica_subtipo = this._calcDonutSegments(data.grafica_subtipo || []);
        const maxDia = Math.max(...(data.grafica_diaria || []).map(d => d.reservas), 1);
        data.grafica_diaria = (data.grafica_diaria || []).map(d => ({
            ...d,
            pct: Math.round((d.reservas / maxDia) * 100),
        }));
        data.grafica_ingresos_mes    = data.grafica_ingresos_mes    || [];
        data.grafica_ocupaciones_mes = data.grafica_ocupaciones_mes || [];

        // ← NUEVO: bonos_activos ya viene del backend
        data.bonos_activos = data.bonos_activos || 0;

        return data;
    }

    _calcDonutSegments(subtipos) {
        const r = 54;
        const circum = 2 * Math.PI * r;
        let acumulado = 0;
        return subtipos.map(s => {
            const dash   = (s.pct / 100) * circum;
            const gap    = circum - dash;
            const offset = -(acumulado / 100) * circum;
            acumulado   += s.pct;
            return {
                ...s,
                dash_array:  `${dash.toFixed(2)} ${gap.toFixed(2)}`,
                dash_offset: offset.toFixed(2),
            };
        });
    }

    onPeriodoChange(ev) {
        this.state.periodo = ev.target.value;
        this._loadData();
    }

    onSubtipoChange(ev) {
        this.state.filtroSubtipo = ev.target.value || null;
        this._loadData();
    }

    onRefresh() {
        this._loadData();
    }

    // ── NUEVO: abre la vista de bonos activos ────────────────────────────
    async openBonos() {
        await this.actionService.doAction(
            "centro_canino_tumburu.action_sale_order_line_bono"
        );
    }

    async openOcupaciones(filtro) {
        const hoy = new Date().toISOString().slice(0, 10);

        if (filtro === "alertas") {
            await this.actionService.doAction(
                "centro_canino_tumburu.action_ocupacion_activas"
            );
            return;
        }

        // "in" abre la misma vista que el menú HOY (kanban dashboard agrupado por estado)
        if (filtro === "in") {
            await this.actionService.doAction(
                "centro_canino_tumburu.action_ocupacion_hoy"
            );
            return;
        }

        const domains = {
            "checkin":  [["estado", "=", "1_reservas"], ["fecha_entrada_date", "=", hoy]],
            "checkout": [["estado", "=", "2_in"], ["fecha_salida_date", "=", hoy]],
            "reservas": [["estado", "=", "1_reservas"]],
        };

        await this.actionService.doAction({
            type:      "ir.actions.act_window",
            name:      "Ocupaciones",
            res_model: "centro_canino.ocupacion",
            view_mode: "kanban,tree,form",
            views:     [[false, "kanban"], [false, "tree"], [false, "form"]],
            domain:    domains[filtro] || [],
            context:   { group_by: "estado", order: "jaula_actual asc" },
            target:    "current",
        });
    }
}

registry.category("actions").add(
    "centro_canino_dashboard.action_dashboard",
    CentroCaninoDashboard
);