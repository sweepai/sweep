import { mock } from "node:test";

jest.mock("openai", () => {
  return {
    OpenAI: jest.fn().mockImplementation(() => ({
      chat: {
        completions: {
          create: jest.fn().mockResolvedValue({
            choices: [{ message: { content: "mocked response" } }],
          }),
        },
      },
    })),
  };
});

const { parseRegexFromOpenAI } = require("./route.ts");

const expectedAnswer = String.raw`import unittest
from unittest.mock import patch

from sweepai.utils.diff import (
    format_contents,
    is_markdown,
    match_string,
    revert_whitespace_changes,
)


class EnhancedDiffTest(unittest.TestCase):
    def test_revert_whitespace_changes(self):
        print("Testing revert_whitespace_changes with typical input")
        original_file_str = "  line1\n  line2\n  line3"
        modified_file_str = "line1\n  line2\n    line3"
        expected_output = "  line1\n  line2\n  line3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_more_whitespace(self):
        print("Testing revert_whitespace_changes with more whitespace in modified file")
        original_file_str = "line1\nline2\nline3"
        modified_file_str = "  line1\n  line2\n  line3"
        expected_output = "line1\nline2\nline3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_non_whitespace_changes(self):
        print("Testing revert_whitespace_changes ensuring non-whitespace changes are not reverted")
        original_file_str = "line1\nline2\nline3"
        modified_file_str = "line4\nline5\nline6"
        expected_output = "line1\nline2\nline3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_same_files(self):
        print("Testing revert_whitespace_changes with identical original and modified files")
        original_file_str = "line1\nline2\nline3"
        modified_file_str = "line1\nline2\nline3"
        expected_output = "line1\nline2\nline3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_empty_files(self):
        print("Testing revert_whitespace_changes with empty original and modified files")
        original_file_str = ""
        modified_file_str = ""
        expected_output = ""
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_whitespace_only_files(self):
        print("Testing revert_whitespace_changes with files containing only whitespace")
        original_file_str = "  \n  \n  "
        modified_file_str = "  \n  \n  "
        expected_output = "  \n  \n  "
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_format_contents(self):
        print("Testing format_contents simplicity")
        file_contents = "line1\nline2\nline3"
        expected_output = "line1\nline2\nline3"
        self.assertEqual(format_contents(file_contents), expected_output)

    @patch("sweepai.utils.diff.find_best_match")
    def test_match_string(self, mock_find_best_match):
        print("Testing match_string function with a mock for find_best_match")
        original = ["line1", "line2", "line3"]
        search = ["line2"]
        mock_find_best_match.return_value = 1
        self.assertEqual(match_string(original, search), 1)

    def test_is_markdown(self):
        print("Testing is_markdown function for markdown file determination")
        filename = "test.md"
        self.assertTrue(is_markdown(filename))


if __name__ == "__main__":
    unittest.main()
`;
const mockResponse = String.raw`<<<<<<< ORIGINAL
class TestDiff(unittest.TestCase):
=======
class EnhancedDiffTest(unittest.TestCase):
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
    def test_revert_whitespace_changes(self):
=======
    def test_revert_whitespace_changes(self):
        print("Testing revert_whitespace_changes with typical input")
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
    def test_revert_whitespace_changes_more_whitespace(self):
=======
    def test_revert_whitespace_changes_more_whitespace(self):
        print("Testing revert_whitespace_changes with more whitespace in modified file")
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
    def test_revert_whitespace_changes_non_whitespace_changes(self):
=======
    def test_revert_whitespace_changes_non_whitespace_changes(self):
        print("Testing revert_whitespace_changes ensuring non-whitespace changes are not reverted")
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
    def test_revert_whitespace_changes_same_files(self):
=======
    def test_revert_whitespace_changes_same_files(self):
        print("Testing revert_whitespace_changes with identical original and modified files")
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
    def test_revert_whitespace_changes_empty_files(self):
=======
    def test_revert_whitespace_changes_empty_files(self):
        print("Testing revert_whitespace_changes with empty original and modified files")
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
    def test_revert_whitespace_changes_whitespace_only_files(self):
=======
    def test_revert_whitespace_changes_whitespace_only_files(self):
        print("Testing revert_whitespace_changes with files containing only whitespace")
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
    def test_format_contents(self):
=======
    def test_format_contents(self):
        print("Testing format_contents simplicity")
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
    @patch("sweepai.utils.diff.find_best_match")
    def test_match_string(self, mock_find_best_match):
=======
    @patch("sweepai.utils.diff.find_best_match")
    def test_match_string(self, mock_find_best_match):
        print("Testing match_string function with a mock for find_best_match")
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
    def test_is_markdown(self):
=======
    def test_is_markdown(self):
        print("Testing is_markdown function for markdown file determination")
>>>>>>> MODIFIED`;
const mockFileContents = String.raw`import unittest
from unittest.mock import patch

from sweepai.utils.diff import (
    format_contents,
    is_markdown,
    match_string,
    revert_whitespace_changes,
)


class TestDiff(unittest.TestCase):
    def test_revert_whitespace_changes(self):
        original_file_str = "  line1\n  line2\n  line3"
        modified_file_str = "line1\n  line2\n    line3"
        expected_output = "  line1\n  line2\n  line3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_more_whitespace(self):
        original_file_str = "line1\nline2\nline3"
        modified_file_str = "  line1\n  line2\n  line3"
        expected_output = "line1\nline2\nline3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_non_whitespace_changes(self):
        original_file_str = "line1\nline2\nline3"
        modified_file_str = "line4\nline5\nline6"
        expected_output = "line1\nline2\nline3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_same_files(self):
        original_file_str = "line1\nline2\nline3"
        modified_file_str = "line1\nline2\nline3"
        expected_output = "line1\nline2\nline3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_empty_files(self):
        original_file_str = ""
        modified_file_str = ""
        expected_output = ""
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_revert_whitespace_changes_whitespace_only_files(self):
        original_file_str = "  \n  \n  "
        modified_file_str = "  \n  \n  "
        expected_output = "  \n  \n  "
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_format_contents(self):
        file_contents = "line1\nline2\nline3"
        expected_output = "line1\nline2\nline3"
        self.assertEqual(format_contents(file_contents), expected_output)

    @patch("sweepai.utils.diff.find_best_match")
    def test_match_string(self, mock_find_best_match):
        original = ["line1", "line2", "line3"]
        search = ["line2"]
        mock_find_best_match.return_value = 1
        self.assertEqual(match_string(original, search), 1)

    def test_is_markdown(self):
        filename = "test.md"
        self.assertTrue(is_markdown(filename))


if __name__ == "__main__":
    unittest.main()
`;

describe("parseRegexFromOpenAI", () => {
  it("given the mock input and response it should return correct answer file", async () => {
    const mockAnswer = parseRegexFromOpenAI(mockResponse, mockFileContents);
    // Assert that the response is as expected
    expect(mockAnswer).toEqual(expectedAnswer);
    expect(1).toEqual(1);
  });
});
