# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class CentroCaninoDashboardController(http.Controller):

    @http.route(
        '/centro_canino/dashboard/data',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def get_data(self, periodo='30', filtro_subtipo=None, **kwargs):
        try:
            data = request.env['centro_canino.dashboard'].get_dashboard_data(
                periodo=str(periodo),
                filtro_subtipo=filtro_subtipo,
            )
            return data
        except Exception as e:
            _logger.exception("Error cargando dashboard")
            return {
                'error': True,
                'message': str(e),
            }

    @http.route(
        '/centro_canino/dashboard/search_candidates',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def search_candidates(self, text='', **kwargs):
        try:
            return request.env['centro_canino.dashboard'].get_search_candidates(text)
        except Exception:
            _logger.exception("Error en search_candidates")
            return []

    @http.route(
        '/centro_canino/dashboard/search_operative',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def search_operative(self, partner_id=None, pet_id=None, **kwargs):
        try:
            return request.env['centro_canino.dashboard'].get_operative_card(
                partner_id=partner_id,
                pet_id=pet_id,
            )
        except Exception:
            _logger.exception("Error en search_operative")
            return {'cliente': None, 'telefono': None, 'items': []}

    @http.route(
        '/centro_canino/dashboard/confirmar_checkin',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def confirmar_checkin(self, order_id=None, pet_id=None, **kwargs):
        try:
            if not order_id:
                return {'ok': False}
            order = request.env['sale.order'].browse(order_id)
            if order.state in ('draft', 'sent'):
                order.action_confirm()
            return {'ok': True}
        except Exception:
            _logger.exception("Error en confirmar_checkin")
            return {'ok': False}