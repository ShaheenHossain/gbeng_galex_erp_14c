# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

from galex import fields, models


class City(models.Model):
    _name = 'res.city'
    _description = 'City'
    _order = 'name'

    name = fields.Char("Name", required=True, translate=True)
    zipcode = fields.Char("Zip")
    country_id = fields.Many2one('res.country', string='Country', required=True)
    state_id = fields.Many2one(
        'res.country.state', 'State', domain="[('country_id', '=', country_id)]")