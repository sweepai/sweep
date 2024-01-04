import unittest
from unittest.mock import MagicMock, patch

from sweepai.agents import assistant_wrapper


class TestAssistantWrapper(unittest.TestCase):

    @patch('sweepai.agents.assistant_wrapper.posthog')
    def test_event_logging(self, mock_posthog):
        mock_chat_logger = MagicMock()
        mock_chat_logger.data.get.return_value = 'test_username'
        assistant_wrapper.openai_assistant_call('test_request', chat_logger=mock_chat_logger)
        mock_posthog.capture.assert_called_with('test_username', 'call_assistant_api', {'query': 'test_request', 'model': 'gpt-4-1106-preview'})

    @patch('sweepai.agents.assistant_wrapper.ChatLogger')
    def test_model_selection(self, mock_chat_logger):
        mock_chat_logger.use_faster_model.return_value = True
        model = assistant_wrapper.openai_assistant_call('test_request', chat_logger=mock_chat_logger)
        self.assertEqual(model, 'gpt-3.5-turbo-1106')

        mock_chat_logger.use_faster_model.return_value = False
        model = assistant_wrapper.openai_assistant_call('test_request', chat_logger=mock_chat_logger)
        self.assertEqual(model, 'gpt-4-1106-preview')

if __name__ == '__main__':
    unittest.main()
