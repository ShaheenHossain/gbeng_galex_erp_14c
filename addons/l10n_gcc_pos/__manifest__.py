# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.
{
    'name': 'Gulf Cooperation Council - Point of Sale',
    'author': 'GalexERP',
    'category': 'Accounting/Localizations/Point of Sale',
    'description': """
GCC POS Localization
=======================================================
    """,
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'l10n_gcc_invoice'],
    'data': [
        'views/assets.xml',
    ],
    'qweb': [
        'static/src/xml/OrderReceipt.xml',
    ],
    'auto_install': True,
}
