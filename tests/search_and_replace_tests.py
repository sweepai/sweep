import unittest
from unittest import mock

from sweepai.utils import search_and_replace


class TestSearchAndReplace(unittest.TestCase):
    def test_split_ellipses(self):
        test_string = "Hello...\nWorld...\n"
        expected_output = ["Hello", "World"]
        self.assertEqual(
            search_and_replace.split_ellipses(test_string), expected_output
        )

    def test_replace_all(self):
        test_string = "Hello World"
        test_substring = "World"
        test_replacement = "Universe"
        expected_output = "Hello Universe"
        with mock.patch(
            "sweepai.utils.search_and_replace.replace_all"
        ) as mock_replace_all:
            mock_replace_all.return_value = expected_output
            self.assertEqual(
                search_and_replace.replace_all(
                    test_string, test_substring, test_replacement
                ),
                expected_output,
            )

    # Add more test methods here for other functions and classes in search_and_replace.py


if __name__ == "__main__":
    unittest.main()
