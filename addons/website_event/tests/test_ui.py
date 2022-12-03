# -*- coding: utf-8 -*-
# Part of GalexERP. See LICENSE file for full copyright and licensing details.

import galex.tests
from galex import tools


@galex.tests.tagged('post_install', '-at_install')
class TestUi(galex.tests.HttpCase):
    def test_admin(self):
        self.start_tour("/", 'event', login='admin', step_delay=100)
