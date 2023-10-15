import unittest
from unittest.mock import Mock
from sweepai.core.sweep_bot import SweepBot

class TestSweepBot(unittest.TestCase):
    def test_fuse_matches(self):
        # Create a SweepBot instance with a mocked prune_modify_snippets_bot
        bot = SweepBot()
        bot.prune_modify_snippets_bot = Mock()

        # Test when length of selected_snippets is greater than 1
        bot.fuse_matches(['snippet1', 'snippet2'])
        bot.prune_modify_snippets_bot.prune_modify_snippets.assert_called_once()

        # Reset the mock
        bot.prune_modify_snippets_bot.reset_mock()

        # Test when length of selected_snippets is not greater than 1
        indices_to_keep = bot.fuse_matches(['snippet1'])
        self.assertEqual(indices_to_keep, [0])
        bot.prune_modify_snippets_bot.prune_modify_snippets.assert_not_called()

if __name__ == "__main__":
    unittest.main()
