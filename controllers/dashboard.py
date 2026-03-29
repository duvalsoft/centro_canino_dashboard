# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class CentroCaninoDashboardController(http.Controller):

    @http.route(
        '/centro_canino/dashboard/data',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def get_data(self, periodo='30', filtro_subtipo=None, **kwargs):
        """
        Endpoint JSON que devuelve los datos del dashboard.
        Llamado desde el componente OWL via fetch/rpc.
        """
        data = request.env['centro_canino.dashboard'].get_dashboard_data(
            periodo=str(periodo),
            filtro_subtipo=filtro_subtipo,
        )
        return data

    @http.route(
        '/centro_canino/dashboard/search_candidates',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def search_candidates(self, text='', **kwargs):
        """
        Paso 1 de búsqueda de recepción.
        Devuelve lista de candidatos (perro + cliente) para desambiguar.
        """
        return request.env['centro_canino.dashboard'].get_search_candidates(text)

    @http.route(
        '/centro_canino/dashboard/search_operative',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def search_operative(self, partner_id=None, pet_id=None, **kwargs):
        """
        Paso 2 de búsqueda de recepción.
        Devuelve la ficha operativa completa de un cliente/perro concreto.
        """
        return request.env['centro_canino.dashboard'].get_operative_card(
            partner_id=partner_id,
            pet_id=pet_id,
        )

    @http.route(
        '/centro_canino/dashboard/confirmar_checkin',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def confirmar_checkin(self, order_id=None, pet_id=None, **kwargs):
        """
        Confirma un pedido en borrador y prepara el checkin.
        """
        if not order_id:
            return {'ok': False}
        order = request.env['sale.order'].browse(order_id)
        if order.state in ('draft', 'sent'):
            order.action_confirm()
        return {'ok': True}  