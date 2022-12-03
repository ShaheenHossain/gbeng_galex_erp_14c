# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenEduCat Inc
#    Copyright (C) 2009-TODAY OpenEduCat Inc(<http://www.openeducat.org>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from . import controllers
from . import models
from . import wizard


# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

from . import controllers
from . import models
from . import wizard
from . import report

from galex import api, SUPERUSER_ID

def _openeducat_post_init(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['publisher_warranty.contract'].update_notification(cron_mode=True)