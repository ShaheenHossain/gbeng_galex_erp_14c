import galex.tests
# Part of GalexERP. See LICENSE file for full copyright and licensing details.


@galex.tests.tagged('post_install', '-at_install')
class TestUi(galex.tests.HttpCase):

    def test_01_sale_tour(self):
        self.start_tour("/web", 'sale_tour', login="admin", step_delay=100)
