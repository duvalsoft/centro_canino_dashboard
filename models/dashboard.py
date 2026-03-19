# -*- coding: utf-8 -*-
from odoo import models, api, fields
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class CentroCaninoDashboard(models.AbstractModel):
    """
    Modelo abstracto que agrupa todos los métodos de cálculo del dashboard.
    No crea tabla en BD — solo expone métodos @api.model.
    """
    _name = 'centro_canino.dashboard'
    _description = 'Dashboard Centro Canino - Métodos de KPI'

    # ------------------------------------------------------------------ #
    #  MÉTODO PRINCIPAL — devuelve TODOS los datos de una vez             #
    # ------------------------------------------------------------------ #
    @api.model
    def get_dashboard_data(self, periodo='30', filtro_subtipo=None):
        """
        Devuelve un dict con todos los KPIs necesarios para el dashboard.

        :param periodo: '7', '30', '90', '365' o 'all'
        :param filtro_subtipo: ID (int) del service.subtype para filtrar, o None
        :return: dict con secciones: hoy, periodo, grafica_diaria, grafica_subtipo, alertas
        """
        hoy = fields.Date.today()
        Ocup = self.env['centro_canino.ocupacion']

        # ── Rango de fechas del periodo ────────────────────────────────── #
        if periodo == 'all':
            fecha_inicio = False
        else:
            dias = int(periodo)
            fecha_inicio = hoy - timedelta(days=dias)

        # ── Dominio base (puede filtrar por subtipo) ──────────────────── #
        def base_domain(extra=None):
            d = []
            if fecha_inicio:
                d += [('fecha_entrada_date', '>=', fecha_inicio)]
            if filtro_subtipo:
                d += [('service_subtype_id', '=', int(filtro_subtipo))]
            if extra:
                d += extra
            return d

        # ================================================================ #
        #  SECCIÓN: HOY                                                    #
        # ================================================================ #
        ocupaciones_in = Ocup.search_count([
            ('estado', '=', '2_in'),
        ] + ([('service_subtype_id', '=', int(filtro_subtipo))] if filtro_subtipo else []))

        total_bungalows = self.env['centro_canino_tumburu.bungalow'].search_count([])
        tasa_ocupacion = round((ocupaciones_in / total_bungalows * 100), 2) if total_bungalows else 0

        pending_checkins = Ocup.search_count([
            ('estado', '=', '1_reservas'),
            ('fecha_entrada_date', '=', hoy),
        ] + ([('service_subtype_id', '=', int(filtro_subtipo))] if filtro_subtipo else []))

        pending_checkouts = Ocup.search_count([
            ('estado', '=', '2_in'),
            ('fecha_salida_date', '=', hoy),
        ] + ([('service_subtype_id', '=', int(filtro_subtipo))] if filtro_subtipo else []))

        # Cuidados especiales: perros dentro con atención médica o comida propia
        alertas_medicas = Ocup.search_count([
            ('estado', '=', '2_in'),
            '|',
            ('tiene_atencion_medica', '=', True),
            ('comida_propia_final', '=', True),
        ] + ([('service_subtype_id', '=', int(filtro_subtipo))] if filtro_subtipo else []))

        hoy_data = {
            'ocupaciones_in':    ocupaciones_in,
            'tasa_ocupacion':    tasa_ocupacion,
            'pending_checkins':  pending_checkins,
            'pending_checkouts': pending_checkouts,
            'alertas_medicas':   alertas_medicas,
            'total_bungalows':   total_bungalows,
        }

        # ================================================================ #
        #  SECCIÓN: PERIODO                                                #
        # ================================================================ #
        total_reservas = Ocup.search_count(base_domain())
        canceladas = Ocup.search_count(base_domain([('estado', '=', '4_cancelada')]))

        query_ingresos = """
            SELECT COALESCE(SUM(so.amount_untaxed), 0)
            FROM sale_order so
            WHERE so.state IN ('sale', 'done')
        """
        params = []
        if fecha_inicio:
            query_ingresos += " AND so.date_order::date >= %s"
            params.append(fecha_inicio)
        if filtro_subtipo:
            query_ingresos += """
                AND EXISTS (
                    SELECT 1 FROM sale_order_line sol2
                    WHERE sol2.order_id = so.id
                      AND sol2.service_subtype_id = %s
                )
            """
            params.append(int(filtro_subtipo))

        self.env.cr.execute(query_ingresos, params)
        ingresos = self.env.cr.fetchone()[0] or 0

        ocups_periodo = Ocup.search(base_domain([('fecha_salida', '!=', False)]))
        dias_promedio = 0
        if ocups_periodo:
            dias_promedio = round(sum(o.dias_estancia for o in ocups_periodo) / len(ocups_periodo), 1)

        periodo_data = {
            'total_reservas': total_reservas,
            'canceladas':     canceladas,
            'ingresos':       float(ingresos),
            'dias_promedio':  dias_promedio,
            'label_periodo':  self._label_periodo(periodo),
        }

        # ================================================================ #
        #  SECCIÓN: GRÁFICA DIARIA (últimos N días, max 30)               #
        # ================================================================ #
        dias_grafica = min(int(periodo) if periodo != 'all' else 30, 30)
        grafica_diaria = []
        for i in range(dias_grafica - 1, -1, -1):
            dia = hoy - timedelta(days=i)
            count = Ocup.search_count(
                [('fecha_entrada_date', '=', dia)] +
                ([('service_subtype_id', '=', int(filtro_subtipo))] if filtro_subtipo else [])
            )
            grafica_diaria.append({
                'fecha':    dia.strftime('%d/%m'),
                'reservas': count,
            })

        # ================================================================ #
        #  SECCIÓN: GRÁFICA POR SUBTIPO DE SERVICIO                       #
        # ================================================================ #
        grafica_subtipo = self._get_distribucion_subtipo(base_domain(), total_reservas)

        # ================================================================ #
        #  SECCIÓN: ÚLTIMAS OCUPACIONES                                    #
        # ================================================================ #
        ultimas = Ocup.search(base_domain(), order='fecha_entrada desc', limit=8)
        ultimas_data = []
        for o in ultimas:
            ultimas_data.append({
                'id':       o.id,
                'perro':    o.pet_id.name if o.pet_id else '-',
                'cliente':  o.cliente_id.name if o.cliente_id else '-',
                'subtipo':  o.service_subtype_id.name if o.service_subtype_id else '-',
                'entrada':  o.fecha_entrada.strftime('%d/%m/%Y %H:%M') if o.fecha_entrada else '-',
                'salida':   o.fecha_salida.strftime('%d/%m/%Y %H:%M') if o.fecha_salida else '-',
                'estado':   o.estado,
                'estado_label': dict(o._fields['estado'].selection).get(o.estado, o.estado),
                'jaula':    o.jaula_actual.name if o.jaula_actual else '-',
                'zona':     o.zona_actual.name if o.zona_actual else '-',
            })

        # ================================================================ #
        #  SUBTIPOS disponibles para el selector                          #
        # ================================================================ #
        subtipos_raw = self.env['service.subtype'].search([])
        subtipos = [{'id': s.id, 'name': s.name} for s in subtipos_raw]

        # ================================================================ #
        #  SECCIÓN: GRÁFICA MENSUAL INGRESOS (últimos 12 meses)           #
        # ================================================================ #
        grafica_ingresos_mes = self._get_grafica_mensual_ingresos(filtro_subtipo)

        # ================================================================ #
        #  SECCIÓN: GRÁFICA MENSUAL OCUPACIONES (últimos 12 meses)        #
        # ================================================================ #
        grafica_ocupaciones_mes = self._get_grafica_mensual_ocupaciones(filtro_subtipo)

        # ================================================================ #
        #  RETORNO                                                         #
        # ================================================================ #
        return {
            'hoy':                     hoy_data,
            'periodo':                 periodo_data,
            'grafica_diaria':          grafica_diaria,
            'grafica_subtipo':         grafica_subtipo,
            'grafica_ingresos_mes':    grafica_ingresos_mes,
            'grafica_ocupaciones_mes': grafica_ocupaciones_mes,
            'ultimas':                 ultimas_data,
            'subtipos':                subtipos,
            'bonos_activos':           self.env['sale.order.line'].search_count([
                ('is_voucher', '=', True),
                ('sesiones_restantes', '>', 0),
            ]),
            'user_is_manager':         self.env.user.has_group(      # ← NUEVO
                'centro_canino_tumburu.group_pet_sitter_manager'
            ),
        }

    # ------------------------------------------------------------------ #
    #  HELPERS                                                            #
    # ------------------------------------------------------------------ #
    def _label_periodo(self, periodo):
        labels = {
            '7':   'Últimos 7 días',
            '30':  'Últimos 30 días',
            '90':  'Últimos 90 días',
            '365': 'Este año',
            'all': 'Todo el historial',
        }
        return labels.get(str(periodo), f'Últimos {periodo} días')

    def _get_distribucion_subtipo(self, base_domain, total):
        """Devuelve lista [{name, count, pct, color}] para la gráfica de donut."""
        Ocup = self.env['centro_canino.ocupacion']
        ocups = Ocup.search(base_domain)
        grupos = {}
        for o in ocups:
            key = (o.service_subtype_id.id, o.service_subtype_id.name if o.service_subtype_id else 'Sin subtipo')
            grupos[key] = grupos.get(key, 0) + 1

        colores = ['#017E84', '#4AACAD', '#a3d5d5', '#6ec6c7', '#025f63',
                   '#80d4d5', '#03969e', '#b8e4e4', '#01575b', '#ceeeed']

        resultado = []
        for idx, ((sid, sname), count) in enumerate(
            sorted(grupos.items(), key=lambda x: x[1], reverse=True)
        ):
            pct = round(count / total * 100, 1) if total else 0
            resultado.append({
                'id':    sid,
                'name':  sname,
                'count': count,
                'pct':   pct,
                'color': colores[idx % len(colores)],
            })
        return resultado

    def _get_grafica_mensual_ingresos(self, filtro_subtipo=None):
        """
        Devuelve lista de los últimos 12 meses con el total de ingresos por mes.
        [{mes, ingresos, ingresos_fmt, pct}]
        """
        hoy = fields.Date.today()
        meses = []
        for i in range(11, -1, -1):
            mes_ref = hoy.replace(day=1) - timedelta(days=i * 28)
            mes_ref = mes_ref.replace(day=1)
            if mes_ref.month == 12:
                fin_mes = mes_ref.replace(year=mes_ref.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                fin_mes = mes_ref.replace(month=mes_ref.month + 1, day=1) - timedelta(days=1)

            query = """
                SELECT COALESCE(SUM(sol.price_subtotal), 0)
                FROM sale_order_line sol
                JOIN centro_canino_ocupacion ocu ON ocu.sale_order_line_id = sol.id
                JOIN sale_order so ON sol.order_id = so.id
                WHERE so.state IN ('sale', 'done')
                  AND ocu.fecha_entrada_date >= %s
                  AND ocu.fecha_entrada_date <= %s
            """
            params = [mes_ref, fin_mes]
            if filtro_subtipo:
                query += " AND ocu.service_subtype_id = %s"
                params.append(int(filtro_subtipo))

            self.env.cr.execute(query, params)
            total = float(self.env.cr.fetchone()[0] or 0)
            meses.append({
                'mes':          mes_ref.strftime('%b %Y'),
                'mes_corto':    mes_ref.strftime('%b'),
                'ingresos':     total,
                'ingresos_fmt': '{:,.0f}€'.format(total).replace(',', '.'),
                'pct':          0,
            })

        max_ing = max((m['ingresos'] for m in meses), default=1) or 1
        for m in meses:
            m['pct'] = round((m['ingresos'] / max_ing) * 100)
        return meses

    def _get_grafica_mensual_ocupaciones(self, filtro_subtipo=None):
        """
        Devuelve lista de los últimos 12 meses con el total de ocupaciones por mes.
        [{mes, ocupaciones, pct}]
        """
        hoy = fields.Date.today()
        Ocup = self.env['centro_canino.ocupacion']
        meses = []
        for i in range(11, -1, -1):
            mes_ref = hoy.replace(day=1) - timedelta(days=i * 28)
            mes_ref = mes_ref.replace(day=1)
            if mes_ref.month == 12:
                fin_mes = mes_ref.replace(year=mes_ref.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                fin_mes = mes_ref.replace(month=mes_ref.month + 1, day=1) - timedelta(days=1)

            domain = [
                ('fecha_entrada_date', '>=', mes_ref),
                ('fecha_entrada_date', '<=', fin_mes),
            ]
            if filtro_subtipo:
                domain.append(('service_subtype_id', '=', int(filtro_subtipo)))

            count = Ocup.search_count(domain)
            meses.append({
                'mes':         mes_ref.strftime('%b %Y'),
                'mes_corto':   mes_ref.strftime('%b'),
                'ocupaciones': count,
                'pct':         0,
            })

        max_ocu = max((m['ocupaciones'] for m in meses), default=1) or 1
        for m in meses:
            m['pct'] = round((m['ocupaciones'] / max_ocu) * 100)
        return meses