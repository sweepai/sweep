import unittest
from unittest.mock import Mock, patch
from sweepai.agents.modify_bot import ModifyBot

class TestModifyBot(unittest.TestCase):
    def setUp(self):
        self.modify_bot = ModifyBot()

    def test_get_snippets_to_modify(self):
        # Mock the file_change_request object
        file_change_request = Mock()
        file_change_request.instructions = 'instructions'
        
        # Call the method with a test case
        snippet_queries, extraction_terms, analysis_and_identifications_str = self.modify_bot.get_snippets_to_modify(
            file_path='file_path',
            file_contents='file_contents',
            file_change_request=file_change_request,
            chunking=False,
        )
        
        # Assert the output is as expected
        self.assertIsInstance(snippet_queries, list)
        self.assertIsInstance(extraction_terms, list)
        self.assertIsInstance(analysis_and_identifications_str, str)

    def test_fuse_matches(self):
        # Create two MatchToModify instances
        match_a = Mock()
        match_a.start = 1
        match_a.end = 2
        match_a.reason = 'reason_a'
        
        match_b = Mock()
        match_b.start = 3
        match_b.end = 4
        match_b.reason = 'reason_b'
        
        # Call the method with the matches
        fused_match = self.modify_bot.fuse_matches(match_a, match_b)
        
        # Assert the output is as expected
        self.assertEqual(fused_match.start, 1)
        self.assertEqual(fused_match.end, 4)
        self.assertEqual(fused_match.reason, 'reason_a & reason_b')

    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()
