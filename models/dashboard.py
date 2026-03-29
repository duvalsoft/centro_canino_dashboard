# -*- coding: utf-8 -*-
from odoo import models, api, fields
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class CentroCaninoDashboard(models.AbstractModel):
    """
    Modelo abstracto que agrupa todos los métodos de cálculo del dashboard.
    No crea tabla en BD — solo expone métodos @api.model.
    """
    _name = 'centro_canino.dashboard'
    _description = 'Dashboard Centro Canino - Métodos de KPI'

    # ================================================================ #
    #  MÉTODO PRINCIPAL                                                 #
    # ================================================================ #

    @api.model
    def get_dashboard_data(self, periodo='30', filtro_subtipo=None):
        hoy  = fields.Date.today()
        Ocup = self.env['centro_canino.ocupacion']

        if periodo == 'all':
            fecha_inicio = False
        else:
            fecha_inicio = hoy - timedelta(days=int(periodo))

        def base_domain(extra=None):
            d = []
            if fecha_inicio:
                d += [('fecha_entrada_date', '>=', fecha_inicio)]
            if filtro_subtipo:
                d += [('service_subtype_id', '=', int(filtro_subtipo))]
            if extra:
                d += extra
            return d

        def subtipo_filter():
            if filtro_subtipo:
                return [('service_subtype_id', '=', int(filtro_subtipo))]
            return []

        # ── HOY ──────────────────────────────────────────────────────
        ocupaciones_in  = Ocup.search_count([('estado', '=', '2_in')] + subtipo_filter())
        total_bungalows = self.env['centro_canino_tumburu.bungalow'].search_count([])
        tasa_ocupacion  = round((ocupaciones_in / total_bungalows * 100), 2) if total_bungalows else 0

        checkin_previstos  = Ocup.search_count(
            [('estado', '!=', '4_cancelada'), ('fecha_entrada_date', '=', hoy)] + subtipo_filter()
        )
        checkin_realizados = Ocup.search_count(
            [('estado', 'in', ['2_in', '3_salidas']), ('fecha_entrada_date', '=', hoy)] + subtipo_filter()
        )
        checkout_previstos  = Ocup.search_count(
            [('estado', '!=', '4_cancelada'), ('fecha_salida_date', '=', hoy)] + subtipo_filter()
        )
        checkout_realizados = Ocup.search_count(
            [('estado', '=', '3_salidas'), ('fecha_salida_date', '=', hoy)] + subtipo_filter()
        )
        alertas_medicas = Ocup.search_count([
            ('estado', '=', '2_in'),
            '|',
            ('tiene_atencion_medica', '=', True),
            ('comida_propia_final',   '=', True),
        ] + subtipo_filter())

        hoy_data = {
            'ocupaciones_in':     ocupaciones_in,
            'tasa_ocupacion':     tasa_ocupacion,
            'total_bungalows':    total_bungalows,
            'checkin_previstos':  checkin_previstos,
            'checkin_realizados': checkin_realizados,
            'checkin_pendientes': max(0, checkin_previstos - checkin_realizados),
            'checkout_previstos':  checkout_previstos,
            'checkout_realizados': checkout_realizados,
            'checkout_pendientes': max(0, checkout_previstos - checkout_realizados),
            'alertas_medicas':    alertas_medicas,
        }

        # ── ESCUELAS ─────────────────────────────────────────────────
        Matricula    = self.env['escuela.matricula']
        Sesion       = self.env['escuela.sesion']
        hoy_inicio   = fields.Datetime.from_string(str(hoy) + ' 00:00:00')
        hoy_fin      = fields.Datetime.from_string(str(hoy) + ' 23:59:59')

        escuelas_data = {
            'matriculas_activas':       Matricula.search_count([('state', '=', 'activa')]),
            'perros_en_centro_escuela': Matricula.search_count([
                ('state', '=', 'activa'),
                ('perro_en_centro', '=', True),
            ]),
            'sesiones_hoy': Sesion.search_count([
                ('date_start', '>=', hoy_inicio),
                ('date_start', '<=', hoy_fin),
                ('state', '!=', 'finished'),
            ]),
        }

        # ── PERIODO ──────────────────────────────────────────────────
        total_reservas = Ocup.search_count(base_domain())
        canceladas     = Ocup.search_count(base_domain([('estado', '=', '4_cancelada')]))

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
            dias_promedio = round(
                sum(o.dias_estancia for o in ocups_periodo) / len(ocups_periodo), 1
            )

        periodo_data = {
            'total_reservas': total_reservas,
            'canceladas':     canceladas,
            'ingresos':       float(ingresos),
            'dias_promedio':  dias_promedio,
            'label_periodo':  self._label_periodo(periodo),
        }

        # ── GRÁFICA DIARIA ───────────────────────────────────────────
        dias_grafica   = min(int(periodo) if periodo != 'all' else 30, 30)
        grafica_diaria = []
        for i in range(dias_grafica - 1, -1, -1):
            dia   = hoy - timedelta(days=i)
            count = Ocup.search_count(
                [('fecha_entrada_date', '=', dia)] + subtipo_filter()
            )
            grafica_diaria.append({
                'fecha':    dia.strftime('%d/%m'),
                'reservas': count,
            })

        # ── GRÁFICA SUBTIPO ──────────────────────────────────────────
        grafica_subtipo = self._get_distribucion_subtipo(base_domain(), total_reservas)

        # ── ÚLTIMAS OCUPACIONES ──────────────────────────────────────
        ultimas      = Ocup.search(base_domain(), order='fecha_entrada desc', limit=8)
        ultimas_data = []
        for o in ultimas:
            ultimas_data.append({
                'id':          o.id,
                'perro':       o.pet_id.name if o.pet_id else '-',
                'cliente':     o.cliente_id.name if o.cliente_id else '-',
                'subtipo':     o.service_subtype_id.name if o.service_subtype_id else '-',
                'entrada':     o.fecha_entrada.strftime('%d/%m/%Y %H:%M') if o.fecha_entrada else '-',
                'salida':      o.fecha_salida.strftime('%d/%m/%Y %H:%M') if o.fecha_salida else '-',
                'estado':      o.estado,
                'estado_label': dict(o._fields['estado'].selection).get(o.estado, o.estado),
                'jaula':       o.jaula_actual.name if o.jaula_actual else '-',
                'zona':        o.zona_actual.name if o.zona_actual else '-',
            })

        # ── SUBTIPOS ─────────────────────────────────────────────────
        subtipos = [
            {'id': s.id, 'name': s.name}
            for s in self.env['service.subtype'].search([])
        ]

        # ── RETORNO ──────────────────────────────────────────────────
        return {
            'hoy':                     hoy_data,
            'escuelas':                escuelas_data,
            'periodo':                 periodo_data,
            'grafica_diaria':          grafica_diaria,
            'grafica_subtipo':         grafica_subtipo,
            'grafica_ingresos_mes':    self._get_grafica_mensual_ingresos(filtro_subtipo),
            'grafica_ocupaciones_mes': self._get_grafica_mensual_ocupaciones(filtro_subtipo),
            'ultimas':                 ultimas_data,
            'subtipos':                subtipos,
            'bonos_activos':           self.env['sale.order.line'].search_count([
                ('is_voucher',     '=', True),
                ('order_id.state', 'in', ['sale', 'done']),
                ('estado_bono',    '=', 'activo'),
            ]),
            'user_is_manager': self.env.user.has_group(
                'centro_canino_tumburu.group_pet_sitter_manager'
            ),
        }

    # ================================================================ #
    #  BÚSQUEDA DE RECEPCIÓN — PASO 1                                  #
    # ================================================================ #

    @api.model
    def get_search_candidates(self, text):
        """
        Devuelve lista de candidatos (perro + cliente) para desambiguar.
        """
        if not text or len(text) < 3:
            return []

        text     = text.strip()
        Pet      = self.env['pet.information']
        Partner  = self.env['res.partner']

        pets = Pet.search([('name', 'ilike', text)], limit=20)

        clientes = Partner.search([
            '|', '|', '|',
            ('name',   'ilike', text),
            ('phone',  'ilike', text),
            ('mobile', 'ilike', text),
            ('email',  'ilike', text),
        ], limit=10)

        if clientes:
            pets |= Pet.search([('customer_id', 'in', clientes.ids)])

        candidatos = []
        vistos     = set()

        for pet in pets:
            key = (pet.id, pet.customer_id.id if pet.customer_id else 0)
            if key in vistos:
                continue
            vistos.add(key)

            imagen = False
            if pet.image_medium:
                imagen = (
                    pet.image_medium.decode('utf-8')
                    if isinstance(pet.image_medium, bytes)
                    else pet.image_medium
                )

            partner = pet.customer_id
            candidatos.append({
                'pet_id':        pet.id,
                'pet_name':      pet.name,
                'pet_image':     imagen,
                'partner_id':    partner.id if partner else False,
                'partner_name':  partner.name if partner else 'Sin propietario',
                'partner_phone': partner.mobile or partner.phone or False,
            })

        return candidatos

    # ================================================================ #
    #  BÚSQUEDA DE RECEPCIÓN — PASO 2                                  #
    # ================================================================ #

    @api.model
    def get_operative_card(self, partner_id=None, pet_id=None):
        """
        Devuelve la ficha operativa completa para un cliente/perro concreto.
        """
        Ocup  = self.env['centro_canino.ocupacion']
        items = []

        partner = (
            self.env['res.partner'].browse(partner_id)
            if partner_id
            else self.env['res.partner']
        )
        pet = (
            self.env['pet.information'].browse(pet_id)
            if pet_id
            else self.env['pet.information']
        )

        if partner and partner.id:
            todos_pets = self.env['pet.information'].search([
                ('customer_id', '=', partner.id)
            ])
        elif pet and pet.id:
            todos_pets = pet
            partner    = pet.customer_id
        else:
            return {'cliente': None, 'telefono': None, 'items': []}

        if not todos_pets:
            return {'cliente': None, 'telefono': None, 'items': []}

        pet_ids = todos_pets.ids

        # ── VIVOS: ocupaciones activas ────────────────────────────────
        for oc in Ocup.search(
            [('estado', '=', '2_in'), ('pet_id', 'in', pet_ids)],
            order='fecha_entrada asc'
        ):
            subtipo = oc.service_subtype_id.name or ''
            jaula   = oc.jaula_actual.name or 'Sin jaula'
            items.append(self._search_item(
                bloque='vivo',
                pet=oc.pet_id.name,
                titulo='Estancia activa',
                descripcion=subtipo + ' · ' + jaula,
                fecha=oc.fecha_salida_date,
                source_model='centro_canino.ocupacion',
                source_id=oc.id,
                accion='ver_ocupacion',
                accion_label='Ver ocupacion',
            ))

        # ── VIVOS: bonos activos ──────────────────────────────────────
        SaleLine = self.env['sale.order.line']
        for bono in SaleLine.search([
            ('is_voucher',     '=', True),
            ('order_id.state', 'in', ['sale', 'done']),
            ('estado_bono',    '=', 'activo'),
            ('petinfo_id',     'in', pet_ids),
        ]):
            total  = getattr(bono.product_id, 'session_count', 0) or 0
            usados = getattr(bono, 'sessions_used', 0) or 0
            rest   = max(total - usados, 0)
            desc   = (str(rest) + ' de ' + str(total) + ' restantes') if total else 'Bono activo'
            items.append(self._search_item(
                bloque='vivo',
                pet=bono.petinfo_id.name if bono.petinfo_id else '-',
                titulo='Bono: ' + (bono.product_id.name or ''),
                descripcion=desc,
                fecha=None,
                source_model='sale.order.line',
                source_id=bono.id,
                accion='usar_bono',
                accion_label='Usar bono',
            ))

        # ── VIVOS: matrículas activas ─────────────────────────────────
        Matricula = self.env['escuela.matricula']
        for m in Matricula.search([
            ('state',  'in', ['activa', 'en_espera']),
            ('pet_id', 'in', pet_ids),
        ]):
            items.append(self._search_item(
                bloque='vivo',
                pet=m.pet_id.name if m.pet_id else '-',
                titulo='Matricula: ' + (m.product_id.name or 'Escuela'),
                descripcion=str(len(m.sesion_ids)) + ' sesiones registradas',
                fecha=m.fecha_inicio,
                source_model='escuela.matricula',
                source_id=m.id,
                accion='ver_matricula',
                accion_label='Ver matricula',
            ))

        # ── ESPERA: reservas pendientes ───────────────────────────────
        for oc in Ocup.search(
            [('estado', '=', '1_reservas'), ('pet_id', 'in', pet_ids)],
            order='fecha_entrada asc'
        ):
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

        # ── ESPERA: presupuestos sin confirmar ────────────────────────
        if partner and partner.id:
            Order = self.env['sale.order']
            for order in Order.search([
                ('state',      'in', ['draft', 'sent']),
                ('partner_id', '=',  partner.id),
            ], order='date_order asc'):
                lineas_pet = order.order_line.filtered(
                    lambda l: l.petinfo_id and l.petinfo_id.id in pet_ids
                )
                if not lineas_pet:
                    continue
                pet_names = ', '.join(
                    l.petinfo_id.name for l in lineas_pet if l.petinfo_id
                )
                desc = (
                    str(len(lineas_pet)) + ' lineas · '
                    + str(round(order.amount_total, 2)) + 'EUR'
                )
                items.append(self._search_item(
                    bloque='espera',
                    pet=pet_names,
                    titulo='Presupuesto sin confirmar: ' + order.name,
                    descripcion=desc,
                    fecha=fields.Date.to_date(order.date_order) if order.date_order else None,
                    source_model='sale.order',
                    source_id=order.id,
                    accion='confirmar_checkin',
                    accion_label='Confirmar y hacer check-in',
                ))

        # ── HISTÓRICO ─────────────────────────────────────────────────
        for oc in Ocup.search(
            [('estado', 'in', ['3_salidas', '4_cancelada']), ('pet_id', 'in', pet_ids)],
            limit=5,
            order='fecha_salida desc'
        ):
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
            'cliente':  partner.name if partner and partner.id else None,
            'telefono': (partner.mobile or partner.phone or None) if partner and partner.id else None,
            'items':    items,
        }

    # ================================================================ #
    #  HELPERS                                                          #
    # ================================================================ #

    def _search_item(self, bloque, pet, titulo, descripcion,
                     fecha, source_model, source_id, accion, accion_label):
        fecha_display = None
        if fecha:
            today = fields.Date.today()
            if fecha == today:
                fecha_display = 'Hoy'
            elif fecha == today + timedelta(days=1):
                fecha_display = 'Manana'
            else:
                fecha_display = (
                    fecha.strftime('%d/%m/%Y')
                    if hasattr(fecha, 'strftime')
                    else str(fecha)
                )
        return {
            'bloque':        bloque,
            'pet':           pet or '-',
            'titulo':        titulo,
            'descripcion':   descripcion or '',
            'fecha_display': fecha_display,
            'source_model':  source_model,
            'source_id':     source_id,
            'accion':        accion,
            'accion_label':  accion_label,
        }

    def _label_periodo(self, periodo):
        labels = {
            '7':   'Ultimos 7 dias',
            '30':  'Ultimos 30 dias',
            '90':  'Ultimos 90 dias',
            '365': 'Este ano',
            'all': 'Todo el historial',
        }
        return labels.get(str(periodo), 'Ultimos ' + str(periodo) + ' dias')

    def _get_distribucion_subtipo(self, base_domain, total):
        Ocup   = self.env['centro_canino.ocupacion']
        ocups  = Ocup.search(base_domain)
        grupos = {}
        for o in ocups:
            sid   = o.service_subtype_id.id
            sname = o.service_subtype_id.name if o.service_subtype_id else 'Sin subtipo'
            key   = (sid, sname)
            grupos[key] = grupos.get(key, 0) + 1

        colores = [
            '#017E84', '#4AACAD', '#a3d5d5', '#6ec6c7', '#025f63',
            '#80d4d5', '#03969e', '#b8e4e4', '#01575b', '#ceeeed',
        ]
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
        hoy   = fields.Date.today()
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
                'ingresos_fmt': '{:,.0f}EUR'.format(total).replace(',', '.'),
                'pct':          0,
            })

        max_ing = max((m['ingresos'] for m in meses), default=1) or 1
        for m in meses:
            m['pct'] = round((m['ingresos'] / max_ing) * 100)
        return meses

    def _get_grafica_mensual_ocupaciones(self, filtro_subtipo=None):
        hoy  = fields.Date.today()
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