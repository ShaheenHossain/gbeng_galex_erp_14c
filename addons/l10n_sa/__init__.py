# -*- encoding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

from galex import api, SUPERUSER_ID

def load_translations(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.ref('l10n_sa.account_arabic_coa_general').process_coa_translations()