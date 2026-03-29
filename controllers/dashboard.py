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
    @http.route('/centro_canino/dashboard/search', type='json', auth='user')
    def dashboard_search(self, text='', **kwargs):
        return request.env['centro_canino.dashboard'].search_recepcion(text)

    @http.route('/centro_canino/dashboard/confirmar_checkin', type='json', auth='user')
    def confirmar_checkin(self, order_id=None, pet_id=None, **kwargs):
        if not order_id:
            return {'ok': False}
        order = request.env['sale.order'].browse(order_id)
        if order.state in ('draft', 'sent'):
            order.action_confirm()
        return {'ok': True}
