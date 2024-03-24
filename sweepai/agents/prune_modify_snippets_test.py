import unittest
from unittest.mock import patch
from sweepai.agents.prune_modify_snippets import PruneModifySnippets

class TestPruneModifySnippets(unittest.TestCase):
    def setUp(self):
        self.pms = PruneModifySnippets()

    @patch.object(PruneModifySnippets, 'chat')
    def test_prune_modify_snippets(self, mock_chat):
        mock_chat.return_value = "<snippets_to_edit>\n<index>0</index>\n<index>1</index>\n</snippets_to_edit>"
        snippets = ["snippet1", "snippet2", "snippet3"]
        file_path = "test_file_path"
        old_code = "test_old_code"
        request = "test_request"
        result = self.pms.prune_modify_snippets(snippets, file_path, old_code, request)
        self.assertEqual(result, [0, 1])

        mock_chat.return_value = "<snippets_to_edit>\n</snippets_to_edit>"
        result = self.pms.prune_modify_snippets(snippets, file_path, old_code, request)
        self.assertEqual(result, [])

    def tearDown(self):
        del self.pms
