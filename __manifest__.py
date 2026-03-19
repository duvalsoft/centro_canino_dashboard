# -*- coding: utf-8 -*-
{
    'name': 'Centro Canino - Dashboard',
    'version': '16.0.1.0.0',
    'category': 'Services',
    'summary': 'Dashboard de gestión del centro canino',
    'description': 'Dashboard con KPIs de ocupaciones, check-ins, ingresos y distribución por subtipo de servicio.',
    'author': 'Tu Empresa',
    'depends': ['centro_canino_tumburu'],   # ← pon aquí el nombre técnico de tu módulo principal
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_action.xml',
        'views/sale_line_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'centro_canino_dashboard/static/src/css/dashboard.css',
            'centro_canino_dashboard/static/src/xml/dashboard.xml',
            'centro_canino_dashboard/static/src/js/dashboard.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
