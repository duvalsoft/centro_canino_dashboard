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
