import unittest
from unittest.mock import patch
from sweepai.agents.refactor_bot import RefactorBot, serialize, deserialize, extract_method

class TestRefactorBot(unittest.TestCase):

    def setUp(self):
        self.refactor_bot = RefactorBot()

    def test_serialize(self):
        self.assertEqual(serialize("'var'"), "__APOSTROPHE__var__APOSTROPHE__")

    def test_deserialize(self):
        self.assertEqual(deserialize("__APOSTROPHE__var__APOSTROPHE__"), "'var'")

    def test_extract_method(self):
        snippet = "def hello():\n    print('Hello, World!')"
        file_path = "test.py"
        method_name = "hello"
        project_name = "test_project"
        result, _ = extract_method(snippet, file_path, method_name, project_name)
        self.assertIn("def hello():", result)

    @patch('sweepai.agents.refactor_bot.ChatGPT')
    def test_refactor_snippets(self, mock_chat_gpt):
        additional_messages = []
        snippets_str = ""
        file_path = ""
        update_snippets_code = ""
        request = ""
        changes_made = ""
        cloned_repo = None
        self.refactor_bot.refactor_snippets(additional_messages, snippets_str, file_path, update_snippets_code, request, changes_made, cloned_repo)
        mock_chat_gpt.assert_called()

    @patch('sweepai.agents.refactor_bot.ChatGPT')
    def test_get_snippets_to_modify(self, mock_chat_gpt):
        file_path = ""
        file_contents = ""
        file_change_request = ""
        chunking = False
        self.refactor_bot.get_snippets_to_modify(file_path, file_contents, file_change_request, chunking)
        mock_chat_gpt.assert_called()

    @patch('sweepai.agents.refactor_bot.ChatGPT')
    def test_update_file(self, mock_chat_gpt):
        file_path = ""
        file_contents = ""
        file_change_request = ""
        snippet_queries = ""
        extraction_terms = ""
        chunking = False
        analysis_and_identification = ""
        self.refactor_bot.update_file(file_path, file_contents, file_change_request, snippet_queries, extraction_terms, chunking, analysis_and_identification)
        mock_chat_gpt.assert_called()

if __name__ == '__main__':
    unittest.main()
