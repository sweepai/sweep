import unittest

from sweepai.agents.modify_bot import ModifyBot


class TestModifyBot(unittest.TestCase):
    def setUp(self):
        self.modify_bot = ModifyBot()


# Removed test_fuse_matches method as it was testing a non-existent method

if __name__ == "__main__":
    unittest.main()
