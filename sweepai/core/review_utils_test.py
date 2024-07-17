import unittest
from sweepai.core.review_utils import add_line_numbers_to_text

class TestReviewUtils(unittest.TestCase):
    def test_add_line_numbers_to_text_empty_string(self):
        result = add_line_numbers_to_text("")
        self.assertEqual(result, "0 ")

    def test_add_line_numbers_to_text_non_empty_string(self):
        test_text = "Hello\nWorld\nThis is a test"
        expected_result = "0 Hello\n1 World\n2 This is a test"
        result = add_line_numbers_to_text(test_text)
        self.assertEqual(result, expected_result)

if __name__ == '__main__':
    unittest.main()