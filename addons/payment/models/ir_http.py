# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

from galex import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_translation_frontend_modules_name(cls):
        mods = super(IrHttp, cls)._get_translation_frontend_modules_name()
        return mods + ['payment']