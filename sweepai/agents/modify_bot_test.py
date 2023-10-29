import unittest
from unittest.mock import Mock
from sweepai.agents.modify_bot import ModifyBot, MatchToModify

class TestModifyBot(unittest.TestCase):
    def setUp(self):
        self.modify_bot = ModifyBot()

    def test_fuse_matches(self):
        match1 = MatchToModify(start=1, end=5, reason="reason1")
        match2 = MatchToModify(start=4, end=8, reason="reason2")

        result = self.modify_bot.fuse_matches(match1, match2)

        self.assertEqual(result.start, 1)
        self.assertEqual(result.end, 8)
        self.assertEqual(result.reason, "reason1 & reason2")

        match1 = MatchToModify(start=1, end=5, reason="reason1")
        match2 = MatchToModify(start=5, end=8, reason="reason2")

        result = self.modify_bot.fuse_matches(match1, match2)

        self.assertEqual(result.start, 1)
        self.assertEqual(result.end, 8)
        self.assertEqual(result.reason, "reason1 & reason2")

        match1 = MatchToModify(start=1, end=5, reason="reason1")
        match2 = MatchToModify(start=6, end=8, reason="reason2")

        result = self.modify_bot.fuse_matches(match1, match2)

        self.assertEqual(result.start, 1)
        self.assertEqual(result.end, 5)
        self.assertEqual(result.reason, "reason1")

if __name__ == "__main__":
    unittest.main()
