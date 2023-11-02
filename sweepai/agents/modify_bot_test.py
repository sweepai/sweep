import unittest
from unittest.mock import patch
from sweepai.agents.modify_bot import ModifyBot, SnippetToModify, MatchToModify, strip_backticks

class TestModifyBot(unittest.TestCase):

    def setUp(self):
        self.modify_bot = ModifyBot()

    def test_strip_backticks(self):
        self.assertEqual(self.modify_bot.strip_backticks('```python\n```'), '')
        self.assertEqual(self.modify_bot.strip_backticks('```python\nprint("Hello, World!")\n```'), 'print("Hello, World!")')

    def test_SnippetToModify(self):
        snippet_to_modify = SnippetToModify(snippet='snippet', reason='reason')
        self.assertEqual(snippet_to_modify.snippet, 'snippet')
        self.assertEqual(snippet_to_modify.reason, 'reason')

    def test_MatchToModify(self):
        match_to_modify = MatchToModify(start=0, end=1, reason='reason')
        self.assertEqual(match_to_modify.start, 0)
        self.assertEqual(match_to_modify.end, 1)
        self.assertEqual(match_to_modify.reason, 'reason')

    @patch('sweepai.agents.modify_bot.ChatGPT')
    def test_try_update_file(self, mock_chat_gpt):
        file_path = 'file_path'
        file_contents = 'file_contents'
        file_change_request = 'file_change_request'
        chunking = False
        self.modify_bot.try_update_file(file_path, file_contents, file_change_request, chunking)
        mock_chat_gpt.assert_called()

    @patch('sweepai.agents.modify_bot.ChatGPT')
    def test_get_snippets_to_modify(self, mock_chat_gpt):
        file_path = 'file_path'
        file_contents = 'file_contents'
        file_change_request = 'file_change_request'
        chunking = False
        self.modify_bot.get_snippets_to_modify(file_path, file_contents, file_change_request, chunking)
        mock_chat_gpt.assert_called()

    @patch('sweepai.agents.modify_bot.ChatGPT')
    def test_update_file(self, mock_chat_gpt):
        file_path = 'file_path'
        file_contents = 'file_contents'
        file_change_request = 'file_change_request'
        snippet_queries = 'snippet_queries'
        extraction_terms = 'extraction_terms'
        chunking = False
        analysis_and_identification = 'analysis_and_identification'
        self.modify_bot.update_file(file_path, file_contents, file_change_request, snippet_queries, extraction_terms, chunking, analysis_and_identification)
        mock_chat_gpt.assert_called()

if __name__ == '__main__':
    unittest.main()
