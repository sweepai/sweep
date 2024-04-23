import unittest
from unittest.mock import MagicMock, patch
from sweepai.agents.modify import modify
from sweepai.core.entities import FileChangeRequest
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import ClonedRepo

class TestModify(unittest.TestCase):
    def setUp(self):
        self.fcrs = [FileChangeRequest(filename="file1.py", instructions="Modify file1")]
        self.request = "Please modify the files"
        self.cloned_repo = MagicMock(spec=ClonedRepo)
        self.relevant_filepaths = ["file1.py", "file2.py"]
        self.chat_logger = MagicMock(spec=ChatLogger)

    @patch("sweepai.agents.modify.ChatGPT")
    def test_modify_success(self, mock_chatgpt):
        # Set up mock ChatGPT responses
        mock_chatgpt.return_value.chat_anthropic.side_effect = [
            "&lt;function_call&gt;...&lt;/function_call&gt;",
            "DONE"
        ]
        
        result = modify(self.fcrs, self.request, self.cloned_repo, 
                        self.relevant_filepaths, self.chat_logger)

        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)
        # Add more assertions to verify the expected result

    @patch("sweepai.agents.modify.ChatGPT")
    def test_modify_failure(self, mock_chatgpt):
        # Set up mock ChatGPT to raise an exception
        mock_chatgpt.return_value.chat_anthropic.side_effect = Exception("Test exception")

        result = modify(self.fcrs, self.request, self.cloned_repo,
                        self.relevant_filepaths, self.chat_logger)

        self.assertEqual(result, {})
        # Add more assertions to verify the expected error handling

if __name__ == '__main__':
    unittest.main()