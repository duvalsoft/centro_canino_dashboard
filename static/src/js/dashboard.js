/** @odoo-module **/

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
            searchText:    "",
            searchStep:    "idle",
            candidates:    [],
            searchResults: null,
            searchLoading: false,
            selectedPet:   null,
        });

        this.openOcupaciones  = this.openOcupaciones.bind(this);
        this.openBonos        = this.openBonos.bind(this);
        this.onPeriodoChange  = this.onPeriodoChange.bind(this);
        this.onSubtipoChange  = this.onSubtipoChange.bind(this);
        this.onRefresh        = this.onRefresh.bind(this);
        this.openEscuelas     = this.openEscuelas.bind(this);
        this.onSearchInput    = this.onSearchInput.bind(this);
        this.clearSearch      = this.clearSearch.bind(this);
        this.selectCandidate  = this.selectCandidate.bind(this);
        this.openSearchResult = this.openSearchResult.bind(this);

        onWillStart(() => this._loadData());
    }

    // ═══════════════════════════════════════════════════════════════════
    // CARGA DE DATOS DEL DASHBOARD
    // ═══════════════════════════════════════════════════════════════════

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

        data.ahora = data.ahora || {
            ocupaciones: 0,
            bungalows_ocupados: 0,
            tasa_ocupacion: 0,
            total_bungalows: 0,
            desglose: {
                con_pernocta: 0,
                sin_pernocta: 0,
                subtipos: [],
            },
        };

        data.hoy = data.hoy || {
            ocupaciones: 0,
            bungalows_estimados: 0,
            desglose: {
                con_pernocta: 0,
                sin_pernocta: 0,
                subtipos: [],
            },
        };

        data.movimiento = data.movimiento || {
            checkin_previstos: 0,
            checkin_realizados: 0,
            checkin_pendientes: 0,
            checkout_previstos: 0,
            checkout_realizados: 0,
            checkout_pendientes: 0,
            alertas_medicas: 0,
        };

        data.ahora.desglose = data.ahora.desglose || {
            con_pernocta: 0,
            sin_pernocta: 0,
            subtipos: [],
        };
        data.ahora.desglose.subtipos = data.ahora.desglose.subtipos || [];

        data.hoy.desglose = data.hoy.desglose || {
            con_pernocta: 0,
            sin_pernocta: 0,
            subtipos: [],
        };
        data.hoy.desglose.subtipos = data.hoy.desglose.subtipos || [];

        data.periodo = data.periodo || {};
        data.periodo.ingresos = data.periodo.ingresos || 0;
        data.periodo.ingresos_fmt = formatCurrency(data.periodo.ingresos);

        data.ultimas = (data.ultimas || []).map(function(o) {
            return Object.assign({}, o, {
                estado_label: ESTADO_LABELS[o.estado] || o.estado,
                estado_class: ESTADO_CLASS[o.estado]  || "badge-reserva",
            });
        });

        data.grafica_subtipo = this._calcDonutSegments(data.grafica_subtipo || []);

        const maxDia = Math.max.apply(
            null,
            (data.grafica_diaria || []).map(function(d) { return d.reservas; }).concat([1])
        );

        data.grafica_diaria = (data.grafica_diaria || []).map(function(d) {
            return Object.assign({}, d, {
                pct: Math.round((d.reservas / maxDia) * 100),
            });
        });

        data.grafica_ingresos_mes    = data.grafica_ingresos_mes    || [];
        data.grafica_ocupaciones_mes = data.grafica_ocupaciones_mes || [];
        data.bonos_activos           = data.bonos_activos           || 0;
        data.subtipos                = data.subtipos                || [];

        return data;
    }

    _calcDonutSegments(subtipos) {
        const r      = 54;
        const circum = 2 * Math.PI * r;
        let acumulado = 0;
        return subtipos.map(function(s) {
            const dash   = (s.pct / 100) * circum;
            const gap    = circum - dash;
            const offset = -(acumulado / 100) * circum;
            acumulado   += s.pct;
            return Object.assign({}, s, {
                dash_array:  dash.toFixed(2) + " " + gap.toFixed(2),
                dash_offset: offset.toFixed(2),
            });
        });
    }

    // ═══════════════════════════════════════════════════════════════════
    // CONTROLES DEL DASHBOARD
    // ═══════════════════════════════════════════════════════════════════

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

    // ═══════════════════════════════════════════════════════════════════
    // NAVEGACIÓN
    // ═══════════════════════════════════════════════════════════════════

    async openBonos() {
        await this.actionService.doAction(
            "centro_canino_tumburu.action_sale_order_line_bono"
        );
    }

    async openEscuelas(filtro) {
        const dominios = {
            activas: {
                name:   "Matrículas Activas",
                model:  "escuela.matricula",
                domain: [["state", "=", "activa"]],
                views:  [[false, "kanban"], [false, "list"], [false, "form"]],
            },
            en_centro: {
                name:   "Perros en Centro con Matrícula",
                model:  "escuela.matricula",
                domain: [["state", "=", "activa"], ["perro_en_centro", "=", true]],
                views:  [[false, "kanban"], [false, "list"], [false, "form"]],
            },
            sesiones_hoy: {
                name:   "Sesiones de Hoy",
                model:  "escuela.sesion",
                domain: [
                    ["date_start", ">=", new Date().toISOString().slice(0, 10) + " 00:00:00"],
                    ["date_start", "<=", new Date().toISOString().slice(0, 10) + " 23:59:59"],
                    ["state", "!=", "finished"],
                ],
                views:  [[false, "list"], [false, "form"]],
            },
        };

        const cfg = dominios[filtro];
        if (!cfg) return;

        await this.actionService.doAction({
            type:      "ir.actions.act_window",
            name:      cfg.name,
            res_model: cfg.model,
            view_mode: cfg.views.map(function(v) { return v[1]; }).join(","),
            views:     cfg.views,
            domain:    cfg.domain,
            target:    "current",
        });
    }

    async openOcupaciones(filtro) {
        const hoy = new Date().toISOString().slice(0, 10);

        if (filtro === "alertas") {
            await this.actionService.doAction(
                "centro_canino_tumburu.action_ocupacion_activas"
            );
            return;
        }

        if (filtro === "in") {
            await this.actionService.doAction(
                "centro_canino_tumburu.action_ocupacion_hoy"
            );
            return;
        }

        const domains = {
            checkin: [
                ["fecha_entrada_date", "=", hoy],
                ["estado", "!=", "4_cancelada"],
            ],
            checkout: [
                ["fecha_salida_date", "=", hoy],
                ["estado", "!=", "4_cancelada"],
            ],
            reservas: [
                ["estado", "=", "1_reservas"],
            ],
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

    // ═══════════════════════════════════════════════════════════════════
    // BÚSQUEDA DE RECEPCIÓN
    // ═══════════════════════════════════════════════════════════════════

    onSearchInput(ev) {
        const text = ev.target.value || "";
        this.state.searchText = text;

        if (text.length < 3) {
            this.state.searchStep    = "idle";
            this.state.candidates    = [];
            this.state.searchResults = null;
            this.state.selectedPet   = null;
            return;
        }

        clearTimeout(this._searchTimeout);
        const self = this;
        this._searchTimeout = setTimeout(function() {
            self._doCandidateSearch(text);
        }, 400);
    }

    async _doCandidateSearch(text) {
        this.state.searchLoading = true;
        try {
            const res = await this.rpc(
                "/centro_canino/dashboard/search_candidates",
                { text: text }
            );
            if (res.length === 1) {
                await this._loadOperativeCard(res[0]);
            } else if (res.length > 1) {
                this.state.candidates = res;
                this.state.searchStep = "disambiguating";
            } else {
                this.state.candidates    = [];
                this.state.searchStep    = "no_results";
                this.state.searchResults = null;
            }
        } catch (e) {
            console.error("Candidate search error:", e);
        } finally {
            this.state.searchLoading = false;
        }
    }

    async selectCandidate(candidate) {
        this.state.selectedPet   = candidate;
        this.state.searchLoading = true;
        await this._loadOperativeCard(candidate);
    }

    async _loadOperativeCard(candidate) {
        this.state.searchLoading = true;
        try {
            const res = await this.rpc(
                "/centro_canino/dashboard/search_operative",
                {
                    partner_id: candidate.partner_id,
                    pet_id:     candidate.pet_id,
                }
            );
            this.state.searchResults = res;
            this.state.searchStep    = "results";
            this.state.selectedPet   = candidate;
        } catch (e) {
            console.error("Operative card error:", e);
        } finally {
            this.state.searchLoading = false;
        }
    }

    clearSearch() {
        this.state.searchText    = "";
        this.state.searchStep    = "idle";
        this.state.candidates    = [];
        this.state.searchResults = null;
        this.state.selectedPet   = null;
    }

async openSearchResult(result) {
    if (!result.source_model || !result.source_id) return;

    if (result.accion === "confirmar_checkin") {
        await this.rpc(
            "/centro_canino/dashboard/confirmar_checkin",
            {
                order_id: result.source_id,
                pet_id: result.pet_id || null,
            }
        );
    }

    if (result.accion === "usar_bono") {
        const ref = await this.orm.call(
            "ir.model.data",
            "check_object_reference",
            ["centro_canino_tumburu", "view_sale_order_line_bono_form"]
        );

        const bonoFormViewId = ref && ref[1] ? ref[1] : false;

        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Bono",
            res_model: "sale.order.line",
            res_id: result.source_id,
            view_mode: "form",
            views: bonoFormViewId ? [[bonoFormViewId, "form"]] : [[false, "form"]],
            target: "current",
        });
        return;
    }

    await this.actionService.doAction({
        type: "ir.actions.act_window",
        res_model: result.source_model,
        res_id: result.source_id,
        view_mode: "form",
        views: [[false, "form"]],
        target: "current",
    });
}
}

registry.category("actions").add(
    "centro_canino_dashboard.action_dashboard",
    CentroCaninoDashboard
);