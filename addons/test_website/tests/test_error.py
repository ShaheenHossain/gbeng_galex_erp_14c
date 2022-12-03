import galex.tests
from galex.tools import mute_logger


@galex.tests.common.tagged('post_install', '-at_install')
class TestWebsiteError(galex.tests.HttpCase):

    @mute_logger('galex.addons.http_routing.models.ir_http', 'galex.http')
    def test_01_run_test(self):
        self.start_tour("/test_error_view", 'test_error_website')
