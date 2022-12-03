# Part of GalexERP. See LICENSE file for full copyright and licensing details.
from galex import fields, models


class ResCurrency(models.Model):

    _inherit = "res.currency"

    l10n_ar_afip_code = fields.Char('AFIP Code', size=4, help='This code will be used on electronic invoice')
