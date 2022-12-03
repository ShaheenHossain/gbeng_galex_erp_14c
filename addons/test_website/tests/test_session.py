import galex.tests
from galex.tools import mute_logger


@galex.tests.common.tagged('post_install', '-at_install')
class TestWebsiteSession(galex.tests.HttpCase):

    def test_01_run_test(self):
        self.start_tour('/', 'test_json_auth')
