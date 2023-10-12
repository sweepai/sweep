import unittest
from unittest.mock import patch
from sweepai.core import sweep_bot

class TestSweepBot(unittest.TestCase):

    @patch('sweepai.core.sweep_bot.SweepBot.check_for_file_changes')
    @patch('sweepai.core.sweep_bot.SweepBot.trigger_sandbox_run')
    def test_sandbox_run_trigger(self, mock_trigger_sandbox_run, mock_check_for_file_changes):
        # Scenario where there are no changes in the file
        mock_check_for_file_changes.return_value = False
        sweep_bot.SweepBot.sandbox_run_trigger()
        mock_trigger_sandbox_run.assert_not_called()

        # Scenario where there are changes in the file
        mock_check_for_file_changes.return_value = True
        sweep_bot.SweepBot.sandbox_run_trigger()
        mock_trigger_sandbox_run.assert_called_once()

if __name__ == '__main__':
    unittest.main()
