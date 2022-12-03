# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

from galex import api, fields, models, _
from galex.exceptions import UserError
import base64


class AccountInvoiceSend(models.TransientModel):
    _inherit = 'account.invoice.send'
    _description = 'Account Invoice Send'

    edi_format_ids = fields.Many2many(related='invoice_ids.journal_id.edi_format_ids', string="Electronic invoicing")
