# -*- coding: utf-8 -*-

import galex

def migrate(cr, version):
    registry = galex.registry(cr.dbname)
    from galex.addons.account.models.chart_template import migrate_set_tags_and_taxes_updatable
    migrate_set_tags_and_taxes_updatable(cr, registry, 'l10n_de_skr04')
