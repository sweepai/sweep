import unittest

from sweepai.utils.search_and_replace import Match, find_best_match, split_ellipses


class TestSearchAndReplace(unittest.TestCase):
    def test_split_ellipses(self):
        """
        Test the split_ellipses function with a string containing multiple lines separated by ellipses.
        """
        input_string = "line1\n...\nline2\n...\nline3"
        expected_output = ["line1", "line2", "line3"]
        self.assertEqual(split_ellipses(input_string), expected_output)

    def test_find_best_match(self):
        """
        Test the find_best_match function with a query and a string.
        """
        query = "line2"
        string = "line1\nline2\nline3"
        match = find_best_match(query, string)
        self.assertIsInstance(match, Match)
        self.assertEqual(match.start, 6)
        self.assertEqual(match.end, 11)
        self.assertGreater(match.score, 50)


if __name__ == "__main__":
    unittest.main()
