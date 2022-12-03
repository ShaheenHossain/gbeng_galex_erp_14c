# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

import json
import logging
import pprint

from galex import http
from galex.http import request

_logger = logging.getLogger(__name__)


class GalexERPByAdyenController(http.Controller):
    _notification_url = '/payment/galex_adyen/notification'

    @http.route('/payment/galex_adyen/notification', type='json', auth='public', csrf=False)
    def galex_adyen_notification(self):
        data = json.loads(request.httprequest.data)
        _logger.info('Beginning GalexERP by Adyen form_feedback with data %s', pprint.pformat(data)) 
        if data.get('authResult') not in ['CANCELLED']:
            request.env['payment.transaction'].sudo().form_feedback(data, 'galex_adyen')
