# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

{
    'name': 'Italy - E-invoicing',
    'version': '0.3',
    'depends': [
        'l10n_it',
        'fetchmail',
        'account_edi'
    ],
    'author': 'GalexERP',
    'description': """
E-invoice implementation
    """,
    'category': 'Accounting/Localizations/EDI',
    'website': 'http://www.galex.com/',
    'data': [
        'security/ir.model.access.csv',
        'data/account_edi_data.xml',
        'data/invoice_it_template.xml',
        'data/invoice_it_simplified_template.xml',
        'views/l10n_it_view.xml',
        ],
    'demo': [
        'data/account_invoice_demo.xml',
    ],
    'post_init_hook': '_l10n_it_edi_post_init',
    'license': 'LGPL-3',
}
