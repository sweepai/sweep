import unittest
from unittest.mock import MagicMock, patch

from sweepai.agents.modify_bot import FileChangeRequest, ModifyBot


class TestModifyBotTryUpdateFile(unittest.TestCase):
    def setUp(self):
        self.modify_bot = ModifyBot()

        self.mock_get_snippets_to_modify = MagicMock(return_value=({}, {}, {}))
        self.mock_update_file = MagicMock(return_value=("new_file_content", []))
        self.mock_add_auto_imports = MagicMock(return_value="new_file_with_imports")

    @patch("sweepai.agents.modify_bot.ModifyBot.get_snippets_to_modify", new_callable=lambda: self.mock_get_snippets_to_modify)
    @patch("sweepai.agents.modify_bot.ModifyBot.update_file", new_callable=lambda: self.mock_update_file)
    @patch("sweepai.agents.modify_bot.add_auto_imports", new_callable=lambda: self.mock_add_auto_imports)
    def test_try_update_file(self):
        file_path = "test_file_path"
        file_contents = "test_file_contents"
        file_change_request = MagicMock()
        cloned_repo = MagicMock()
        chunking = False

        result = self.modify_bot.try_update_file(file_path, file_contents, file_change_request, cloned_repo, chunking)

        self.assertEqual(result, "new_file_with_imports")
        self.mock_get_snippets_to_modify.assert_called()
        self.mock_update_file.assert_called()
        self.mock_add_auto_imports.assert_called_with(cloned_repo.repo_dir, file_path, "new_file_content")

        self.mock_get_snippets_to_modify = MagicMock(return_value=({}, {}, {}))
        self.mock_update_file = MagicMock(return_value=("new_file_content", []))
        self.mock_add_auto_imports = MagicMock(return_value="new_file_with_imports")
        self.mock_deepcopy = MagicMock()
        self.mock_uuid4 = MagicMock(return_value="1234")

    @patch("sweepai.agents.modify_bot.ModifyBot.get_snippets_to_modify", new_callable=lambda: self.mock_get_snippets_to_modify)
    @patch("sweepai.agents.modify_bot.ModifyBot.update_file", new_callable=lambda: self.mock_update_file)
    @patch("sweepai.agents.modify_bot.add_auto_imports", new_callable=lambda: self.mock_add_auto_imports)
    @patch("copy.deepcopy", new_callable=lambda: self.mock_deepcopy)
    @patch("uuid.uuid4", new_callable=lambda: self.mock_uuid4)
    @patch("sweepai.agents.modify_bot.DEBUG", False)
    def test_try_update_file_with_snippets_to_modify(self):
        file_path = "test_file_path"
        file_contents = "test_file_contents"
        file_change_request = MagicMock()
        cloned_repo = MagicMock()
        chunking = False

        self.modify_bot.fetch_snippets_bot = MagicMock()
        self.modify_bot.prune_modify_snippets_bot = MagicMock()
        self.modify_bot.update_snippets_bot = MagicMock()

        self.mock_get_snippets_to_modify.return_value = ({"snippet": "query"}, ["term"], {"analysis": "identification"})
        self.mock_update_file.return_value = ("new_file_content", ["leftover_comment"])

        result = self.modify_bot.try_update_file(file_path, file_contents, file_change_request, cloned_repo, chunking)

        self.assertEqual(result, "new_file_with_imports")
        self.mock_get_snippets_to_modify.assert_called()
        self.mock_update_file.assert_called()
        self.mock_add_auto_imports.assert_called_with(cloned_repo.repo_dir, file_path, "new_file_content")
class TestModifyBotUpdateFile(unittest.TestCase):
    def setUp(self):
        self.modify_bot = ModifyBot()
        self.mock_prune_modify_snippets = MagicMock()
        self.mock_chat = MagicMock()
        self.mock_extract_leftover_comments = MagicMock()

    @patch("sweepai.agents.modify_bot.ModifyBot.prune_modify_snippets_bot.prune_modify_snippets")
    @patch("sweepai.agents.modify_bot.ModifyBot.update_snippets_bot.chat")
    @patch("sweepai.agents.modify_bot.ModifyBot.extract_leftover_comments_bot.extract_leftover_comments")
    def test_update_file(self, mock_prune_modify_snippets, mock_chat, mock_extract_leftover_comments):
        mock_prune_modify_snippets.return_value = self.mock_prune_modify_snippets
        mock_chat.return_value = self.mock_chat
        mock_extract_leftover_comments.return_value = self.mock_extract_leftover_comments

        # Call the method under test
        result, leftover_comments = self.modify_bot.update_file(
            file_path="test.py",
            file_contents="print("Hello, World!")",
            file_change_request=MagicMock(),
            snippet_queries=[],
            extraction_terms=[],
            chunking=False,
            analysis_and_identification=""
        )

        # Assert that the mocks were called
        mock_prune_modify_snippets.assert_called_once()
        mock_chat.assert_called_once()
        mock_extract_leftover_comments.assert_called_once()

        # Add more assertions as needed to verify the behavior of the method under test

        self.mock_extract_python_span = MagicMock(return_value=MagicMock(content=""))
        self.mock_sliding_window_replacement = MagicMock(return_value=("", []))
        self.mock_finditer = MagicMock(return_value=iter([]))

    @patch("sweepai.agents.modify_bot.extract_python_span", new_callable=lambda: self.mock_extract_python_span)
    @patch("sweepai.agents.modify_bot.sliding_window_replacement", new_callable=lambda: self.mock_sliding_window_replacement)
    @patch("re.finditer", new_callable=lambda: self.mock_finditer)
    @patch("sweepai.agents.modify_bot.DEBUG", False)
    @patch("sweepai.agents.modify_bot.update_snippets_system_prompt_python", "test_prompt")
    @patch("sweepai.agents.modify_bot.update_snippets_prompt_test", "test_prompt")
    @patch("sweepai.agents.modify_bot.update_snippets_prompt", "test_prompt")
    def test_update_file_with_python_file(self):
        file_path = "test_file_path.py"
        file_contents = "test_file_contents"
        file_change_request = MagicMock()
        snippet_queries = []
        extraction_terms = []
        chunking = False
        analysis_and_identification = ""

        result, leftover_comments = self.modify_bot.update_file(file_path, file_contents, file_change_request, snippet_queries, extraction_terms, chunking, analysis_and_identification)

        self.assertEqual(result, file_contents)
        self.assertEqual(leftover_comments, [])
        self.mock_extract_python_span.assert_called()
        self.mock_sliding_window_replacement.assert_called()
        self.mock_finditer.assert_called()
class TestModifyBotGetDiffsMessage(unittest.TestCase):
    def setUp(self):
        self.bot = ModifyBot()
        self.bot.old_file_contents = "old file contents"
        self.bot.current_file_diff = ""
        self.bot.additional_diffs = "additional diffs"
        self.mock_generate_diff = MagicMock(return_value="mock diff")
        self.patcher = patch("sweepai.agents.modify_bot.generate_diff", new=self.mock_generate_diff)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_get_diffs_message(self):
        file_contents = "new file contents"
        expected_message = "\n# Changes Made\nHere are changes we already made to this file:\n<diff>\nmock diff\nadditional diffs\n</diff>\n"
        self.assertEqual(self.bot.get_diffs_message(file_contents), expected_message)

    def tearDown(self):
        self.patcher.stop()

    def test_get_diffs_message_no_changes(self):
        file_contents = "old file contents"
        expected_message = "\n# Changes Made\nHere are changes we already made to this file:\n<diff>\nadditional diffs\n</diff>\n"
        self.assertEqual(self.bot.get_diffs_message(file_contents), expected_message)
class TestModifyBotGetSnippetsToModify(unittest.TestCase):
    def setUp(self):
        self.modify_bot = ModifyBot()
        self.file_path = "test_file_path"
        self.file_contents = "test_file_contents"
        self.file_change_request = FileChangeRequest("test_instructions")

        self.mock_chat = MagicMock()
        self.mock_chat.return_value = "mock chat response"

        self.mock_get_diffs_message = MagicMock()
        self.mock_get_diffs_message.return_value = "mock diffs message"

        self.mock_chunk_code = MagicMock()
        self.mock_chunk_code.return_value = "mock chunk code"

    @patch("sweepai.agents.modify_bot.ModifyBot.get_diffs_message")
    @patch("sweepai.agents.modify_bot.ModifyBot.fetch_snippets_bot.chat")
    @patch("sweepai.agents.modify_bot.chunk_code")
    def test_get_snippets_to_modify(self, mock_chunk_code, mock_chat, mock_get_diffs_message):
        mock_chunk_code.return_value = self.mock_chunk_code.return_value
        mock_chat.return_value = self.mock_chat.return_value
        mock_get_diffs_message.return_value = self.mock_get_diffs_message.return_value

        snippet_queries, extraction_terms, analysis_and_identifications_str = self.modify_bot.get_snippets_to_modify(
            self.file_path, self.file_contents, self.file_change_request)

        # Add your assertions here

        self.mock_chat = MagicMock()
        self.mock_chat.return_value = "mock chat response"

        self.mock_get_diffs_message = MagicMock()
        self.mock_get_diffs_message.return_value = "mock diffs message"

        self.mock_chunk_code = MagicMock()
        self.mock_chunk_code.return_value = "mock chunk code"

        self.mock_search = MagicMock()
        self.mock_search.return_value = MagicMock(group=MagicMock(return_value=""))

        self.mock_findall = MagicMock()
        self.mock_findall.return_value = []

        self.mock_excel_col_to_int = MagicMock()
        self.mock_excel_col_to_int.return_value = 0

    @patch("sweepai.agents.modify_bot.ModifyBot.get_diffs_message")
    @patch("sweepai.agents.modify_bot.ModifyBot.fetch_snippets_bot.chat")
    @patch("sweepai.agents.modify_bot.chunk_code")
    @patch("re.search")
    @patch("re.findall")
    @patch("sweepai.agents.modify_bot.excel_col_to_int")
    @patch("sweepai.agents.modify_bot.fetch_snippets_prompt_with_diff", "test_prompt")
    @patch("sweepai.agents.modify_bot.fetch_snippets_prompt", "test_prompt")
    @patch("sweepai.agents.modify_bot.use_chunking_message", "test_message")
    @patch("sweepai.agents.modify_bot.dont_use_chunking_message", "test_message")
    def test_get_snippets_to_modify_with_diffs(self, mock_chunk_code, mock_chat, mock_get_diffs_message, mock_search, mock_findall, mock_excel_col_to_int):
        mock_chunk_code.return_value = self.mock_chunk_code.return_value
        mock_chat.return_value = self.mock_chat.return_value
        mock_get_diffs_message.return_value = self.mock_get_diffs_message.return_value
        mock_search.return_value = self.mock_search.return_value
        mock_findall.return_value = self.mock_findall.return_value
        mock_excel_col_to_int.return_value = self.mock_excel_col_to_int.return_value

        snippet_queries, extraction_terms, analysis_and_identifications_str = self.modify_bot.get_snippets_to_modify(
            self.file_path, self.file_contents, self.file_change_request, chunking=True)

        self.assertEqual(snippet_queries, [])
        self.assertEqual(extraction_terms, [])
        self.assertEqual(analysis_and_identifications_str, "")
        mock_get_diffs_message.assert_called()
        mock_chat.assert_called()
        mock_search.assert_called()
        mock_findall.assert_called()
        mock_excel_col_to_int.assert_called()

if __name__ == "__main__":
    unittest.main()