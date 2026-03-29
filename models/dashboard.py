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

        # PREVISTOS HOY (todos los que deberían entrar)
        checkin_previstos = Ocup.search_count([
            ('estado', '!=', '4_cancelada'),
            ('fecha_entrada_date', '=', hoy),
        ] + ([('service_subtype_id', '=', int(filtro_subtipo))] if filtro_subtipo else []))


        # REALIZADOS HOY (ya han entrado)
        checkin_realizados = Ocup.search_count([
            ('estado', 'in', ['2_in', '3_salidas']),
            ('fecha_entrada_date', '=', hoy),
        ] + ([('service_subtype_id', '=', int(filtro_subtipo))] if filtro_subtipo else []))


        # PENDIENTES
        pending_checkins = max(0, checkin_previstos - checkin_realizados)

        # PREVISTOS HOY
        checkout_previstos = Ocup.search_count([
            ('estado', '!=', '4_cancelada'),
            ('fecha_salida_date', '=', hoy),
        ] + ([('service_subtype_id', '=', int(filtro_subtipo))] if filtro_subtipo else []))


        # REALIZADOS HOY
        checkout_realizados = Ocup.search_count([
            ('estado', '=', '3_salidas'),
            ('fecha_salida_date', '=', hoy),
        ] + ([('service_subtype_id', '=', int(filtro_subtipo))] if filtro_subtipo else []))


        # PENDIENTES
        pending_checkouts = max(0, checkout_previstos - checkout_realizados)

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
            'checkin_previstos': checkin_previstos,
            'checkin_realizados': checkin_realizados,
            'checkin_pendientes': pending_checkins,
            'checkout_previstos': checkout_previstos,
            'checkout_realizados': checkout_realizados,
            'checkout_pendientes': pending_checkouts,
            'alertas_medicas':   alertas_medicas,
            'total_bungalows':   total_bungalows,
        }

         # ================================================================ #
        #  SECCIÓN: ESCUELAS                                              #
        # ================================================================ #
        Matricula = self.env['escuela.matricula']
        Sesion = self.env['escuela.sesion']
 
        matriculas_activas = Matricula.search_count([
            ('state', '=', 'activa'),
        ])
 
        perros_en_centro_escuela = Matricula.search_count([
            ('state', '=', 'activa'),
            ('perro_en_centro', '=', True),
        ])
 
        # Sesiones que empiezan hoy (fecha_start entre 00:00 y 23:59 de hoy)
        hoy_inicio = fields.Datetime.from_string(str(hoy) + ' 00:00:00')
        hoy_fin    = fields.Datetime.from_string(str(hoy) + ' 23:59:59')
        sesiones_hoy = Sesion.search_count([
            ('date_start', '>=', hoy_inicio),
            ('date_start', '<=', hoy_fin),
            ('state', '!=', 'finished'),
        ])
 
        escuelas_data = {
            'matriculas_activas':       matriculas_activas,
            'perros_en_centro_escuela': perros_en_centro_escuela,
            'sesiones_hoy':             sesiones_hoy,
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
            'escuelas':                escuelas_data,
            'periodo':                 periodo_data,
            'grafica_diaria':          grafica_diaria,
            'grafica_subtipo':         grafica_subtipo,
            'grafica_ingresos_mes':    grafica_ingresos_mes,
            'grafica_ocupaciones_mes': grafica_ocupaciones_mes,
            'ultimas':                 ultimas_data,
            'subtipos':                subtipos,
            'bonos_activos':           self.env['sale.order.line'].search_count([
                ('is_voucher', '=', True),
                ('order_id.state', 'in', ['sale', 'done']),
                ('estado_bono', '=', 'activo'),
            ]),
            'user_is_manager':         self.env.user.has_group(
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
    





    @api.model
    def search_recepcion(self, text):
        """
        Búsqueda unificada para recepción.
        Devuelve resultados agrupados en: vivo, espera, historico.
        """
        if not text or len(text) < 3:
            return {'cliente': None, 'pets': None, 'items': []}

        text = text.strip()
        today = fields.Date.today()

        # ── Encontrar cliente y perros ─────────────────────────────────────
        Partner = self.env['res.partner']
        cliente = Partner.search([
            '|', '|', '|',
            ('name',   'ilike', text),
            ('phone',  'ilike', text),
            ('mobile', 'ilike', text),
            ('email',  'ilike', text),
        ], limit=1)

        Pet = self.env['pet.information']
        pets = Pet.search([('name', 'ilike', text)])
        if cliente:
            pets |= Pet.search([('customer_id', '=', cliente.id)])

        if not cliente and not pets:
            return {'cliente': None, 'pets': None, 'items': []}

        items = []

        # ── BLOQUE VIVO: ocupaciones activas ──────────────────────────────
        Ocup = self.env['centro_canino.ocupacion']
        domain_ocup = [('estado', '=', '2_in')]
        if pets:
            domain_ocup.append(('pet_id', 'in', pets.ids))
        elif cliente:
            domain_ocup.append(('cliente_id', '=', cliente.id))

        for oc in Ocup.search(domain_ocup, order='fecha_entrada asc'):
            items.append(self._search_item(
                bloque='vivo',
                pet=oc.pet_id.name,
                titulo='Estancia activa',
                descripcion=f'{oc.service_subtype_id.name or ""} · {oc.jaula_actual.name or "Sin jaula"}',
                fecha=oc.fecha_salida_date,
                source_model='centro_canino.ocupacion',
                source_id=oc.id,
                accion='ver_ocupacion',
                accion_label='Ver ocupación',
            ))

        # ── BLOQUE VIVO: bonos activos ────────────────────────────────────
        SaleLine = self.env['sale.order.line']
        domain_bono = [
            ('is_voucher', '=', True),
            ('order_id.state', 'in', ['sale', 'done']),
            ('estado_bono', '=', 'activo'),
        ]
        if pets:
            domain_bono.append(('petinfo_id', 'in', pets.ids))
        elif cliente:
            domain_bono.append(('order_id.partner_id', '=', cliente.id))

        for bono in SaleLine.search(domain_bono):
            total    = getattr(bono.product_id, 'session_count', 0) or 0
            usados   = getattr(bono, 'sessions_used', 0) or 0
            rest     = max(total - usados, 0)
            items.append(self._search_item(
                bloque='vivo',
                pet=bono.petinfo_id.name if bono.petinfo_id else '-',
                titulo=f'Bono: {bono.product_id.name}',
                descripcion=f'{rest} de {total} restantes' if total else 'Bono activo',
                fecha=None,
                source_model='sale.order.line',
                source_id=bono.id,
                accion='usar_bono',
                accion_label='Usar bono',
            ))

        # ── BLOQUE VIVO: matrículas activas ──────────────────────────────
        Matricula = self.env['escuela.matricula']
        domain_mat = [('state', 'in', ['activa', 'en_espera'])]
        if pets:
            domain_mat.append(('pet_id', 'in', pets.ids))
        elif cliente:
            domain_mat.append(('cliente_id', '=', cliente.id))

        for m in Matricula.search(domain_mat):
            items.append(self._search_item(
                bloque='vivo',
                pet=m.pet_id.name if m.pet_id else '-',
                titulo=f'Matrícula: {m.product_id.name or "Escuela"}',
                descripcion=f'{len(m.sesion_ids)} sesiones registradas',
                fecha=m.fecha_inicio,
                source_model='escuela.matricula',
                source_id=m.id,
                accion='ver_matricula',
                accion_label='Ver matrícula',
            ))

        # ── BLOQUE ESPERA: reservas pendientes de checkin ─────────────────
        domain_res = [('estado', '=', '1_reservas')]
        if pets:
            domain_res.append(('pet_id', 'in', pets.ids))
        elif cliente:
            domain_res.append(('cliente_id', '=', cliente.id))

        for oc in Ocup.search(domain_res, order='fecha_entrada asc'):
            items.append(self._search_item(
                bloque='espera',
                pet=oc.pet_id.name,
                titulo='Reserva pendiente de entrada',
                descripcion=oc.service_subtype_id.name or '',
                fecha=oc.fecha_entrada_date,
                source_model='centro_canino.ocupacion',
                source_id=oc.id,
                accion='checkin',
                accion_label='Hacer check-in',
            ))

        # ── BLOQUE ESPERA: presupuestos sin confirmar ─────────────────────
        Order = self.env['sale.order']
        domain_ord = [('state', 'in', ['draft', 'sent'])]
        if cliente:
            domain_ord.append(('partner_id', '=', cliente.id))

        for order in Order.search(domain_ord, order='date_order asc'):
            lineas = order.order_line
            if pets:
                lineas = lineas.filtered(
                    lambda l: l.petinfo_id and l.petinfo_id.id in pets.ids
                )
            if not lineas and not cliente:
                continue
            items.append(self._search_item(
                bloque='espera',
                pet=', '.join(
                    l.petinfo_id.name for l in lineas if l.petinfo_id
                ) or '-',
                titulo=f'Presupuesto sin confirmar: {order.name}',
                descripcion=f'{len(lineas)} líneas · {order.amount_total:.2f}€',
                fecha=fields.Date.to_date(order.date_order) if order.date_order else None,
                source_model='sale.order',
                source_id=order.id,
                accion='confirmar_checkin',
                accion_label='Confirmar y hacer check-in',
            ))

        # ── BLOQUE HISTÓRICO ──────────────────────────────────────────────
        domain_hist = [('estado', 'in', ['3_salidas', '4_cancelada'])]
        if pets:
            domain_hist.append(('pet_id', 'in', pets.ids))
        elif cliente:
            domain_hist.append(('cliente_id', '=', cliente.id))

        for oc in Ocup.search(domain_hist, limit=5, order='fecha_salida desc'):
            items.append(self._search_item(
                bloque='historico',
                pet=oc.pet_id.name,
                titulo='Estancia finalizada',
                descripcion=oc.service_subtype_id.name or '',
                fecha=oc.fecha_salida_date,
                source_model='centro_canino.ocupacion',
                source_id=oc.id,
                accion='ver_detalle',
                accion_label='Ver detalle',
            ))

        return {
            'cliente': cliente.name if cliente else None,
            'pets':    ', '.join(pets.mapped('name')) if pets else None,
            'items':   items,
        }

    def _search_item(self, bloque, pet, titulo, descripcion,
                    fecha, source_model, source_id, accion, accion_label):
        """Helper para construir un item de resultado de búsqueda."""
        fecha_display = None
        if fecha:
            today = fields.Date.today()
            if fecha == today:
                fecha_display = 'Hoy'
            elif fecha == today + timedelta(days=1):
                fecha_display = 'Mañana'
            else:
                fecha_display = fecha.strftime('%d/%m/%Y') if hasattr(fecha, 'strftime') else str(fecha)

        return {
            'bloque':       bloque,
            'pet':          pet or '-',
            'titulo':       titulo,
            'descripcion':  descripcion or '',
            'fecha_display': fecha_display,
            'source_model': source_model,
            'source_id':    source_id,
            'accion':       accion,
            'accion_label': accion_label,
        }