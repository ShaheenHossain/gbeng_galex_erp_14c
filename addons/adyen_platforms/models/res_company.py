# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

from galex import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    adyen_account_id = fields.Many2one('adyen.account', string='Adyen Account', readonly=True)
