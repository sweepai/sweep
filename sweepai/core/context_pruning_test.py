import unittest
from unittest.mock import MagicMock, patch

from sweepai.core import context_pruning


class TestContextPruning(unittest.TestCase):

    @patch('sweepai.core.context_pruning.posthog')
    def test_event_logging(self, mock_posthog):
        mock_chat_logger = MagicMock()
        mock_chat_logger.data.get.return_value = 'test_username'
        context_pruning.get_relevant_context('test_query', None, None, mock_chat_logger)
        mock_posthog.capture.assert_called_with('test_username', 'call_assistant_api', {'query': 'test_query', 'model': 'gpt-4-1106-preview'})

    @patch('sweepai.core.context_pruning.ChatLogger')
    def test_model_selection(self, mock_chat_logger):
        mock_chat_logger.use_faster_model.return_value = True
        context = context_pruning.get_relevant_context('test_query', None, None, mock_chat_logger)
        self.assertEqual(context.model, 'gpt-3.5-turbo-1106')

        mock_chat_logger.use_faster_model.return_value = False
        context = context_pruning.get_relevant_context('test_query', None, None, mock_chat_logger)
        self.assertEqual(context.model, 'gpt-4-1106-preview')

if __name__ == '__main__':
    unittest.main()
