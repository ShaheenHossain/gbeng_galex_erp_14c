# Part of GalexERP. See LICENSE file for full copyright and licensing details.

from galex.tests.common import HttpSavepointCase
from galex.addons.sale_product_configurator.tests.common import TestProductConfiguratorCommon
from galex.tests import tagged


@tagged('post_install', '-at_install')
class TestUi(HttpSavepointCase, TestProductConfiguratorCommon):

    def test_01_admin_shop_custom_attribute_value_tour(self):
        # fix runbot, sometimes one pricelist is chosen, sometimes the other...
        pricelists = self.env['website'].get_current_website().get_current_pricelist() | self.env.ref('product.list0')
        self._create_pricelist(pricelists)
        self.start_tour("/", 'a_shop_custom_attribute_value', login="admin")
