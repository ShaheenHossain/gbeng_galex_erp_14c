# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

import galex.tests
from galex.tools import mute_logger


@galex.tests.common.tagged('post_install', '-at_install')
class TestCustomSnippet(galex.tests.HttpCase):

    @mute_logger('galex.addons.http_routing.models.ir_http', 'galex.http')
    def test_01_run_tour(self):
        self.start_tour("/", 'test_custom_snippet', login="admin")
