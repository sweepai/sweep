import unittest
import logging
import traceback
from sweepai.utils.docker_utils import get_latest_docker_version

class TestDockerUtils(unittest.TestCase):
    def test_get_latest_docker_version(self):
        try:
            version = get_latest_docker_version()
            self.assertIsNotNone(version)
        except Exception as error:
            logging.error("An error occurred: %s\n%s", error, traceback.format_exc())

if __name__ == '__main__':
    unittest.main()
