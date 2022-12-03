# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

{
    'name': 'GalexERP Payments by Adyen Payment Acquirer',
    'category': 'Accounting/Payment Acquirers',
    'sequence': 330,
    'summary': 'Payment Acquirer: GalexERP Payments by Adyen',
    'version': '1.0',
    'description': """GalexERP Payments by Adyen""",
    'depends': ['payment', 'adyen_platforms'],
    'data': [
        'views/payment_views.xml',
        'views/payment_galex_by_adyen_templates.xml',
        'data/payment_acquirer_data.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
