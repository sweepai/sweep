import unittest
from datetime import datetime, timedelta

from sweepai.utils.time_utils import time_since


class TestTimeUtils(unittest.TestCase):
    def test_time_since(self):
        past_time = datetime.now() - timedelta(hours=2)
        result = time_since(past_time)
        self.assertIsInstance(result, str)
        self.assertEqual(result, "2 hours ago")
