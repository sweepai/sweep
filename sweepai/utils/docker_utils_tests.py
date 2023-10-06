import unittest
import re
from sweepai.utils.docker_utils import get_latest_docker_version

class TestDockerUtils(unittest.TestCase):
    def test_get_latest_docker_version(self):
        result = get_latest_docker_version()
        self.assertIsInstance(result, str)
        self.assertTrue(re.match('^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', result) is not None)
