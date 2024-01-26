const systemMessagePrompt = `You are a brilliant and meticulous engineer assigned to modify a code file. When you write code, the code works on the first try and is syntactically perfect. You have the utmost care for the code that you write, so you do not make mistakes. Take into account the current code's language, code style and what the user is attempting to accomplish. You are to follow the instructions exactly and do nothing more. If the user requests multiple changes, you must make the changes one at a time and finish each change fully before moving onto the next change.

You MUST respond in the following diff format:

\`\`\`
<<<<<<< ORIGINAL
The first code block to replace. Ensure the indentation is valid.
=======
The new code block to replace the first code block. Ensure the indentation and syntax is valid.
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
The second code block to replace. Ensure the indentation is valid.
=======
The new code block to replace the second code block. Ensure the indentation and syntax is valid.
>>>>>>> MODIFIED
\`\`\`

You may write one or multiple diff hunks. The MODIFIED can be empty.`
const userMessagePrompt = `Your job is to modify the current code file in order to complete the user's request:
<user_request>
{prompt}
</user_request>

Here are the file's current contents:
<file_contents>
{fileContents}
</file_contents>`

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
`
const mockPrompt = String.raw`1. change the class name to something more descriptive
2. add a print to each function that describes what it does, do this at the front of the function `

const prompt1 = systemMessagePrompt + userMessagePrompt.replace('{prompt}', mockPrompt).replace('{fileContents}', mockFileContents)


const axios = require('axios')
axios.post('https://api.together.xyz/v1/completions', {
  "model": "Phind/Phind-CodeLlama-34B-v2",
  "max_tokens": 2500,
  "prompt": "### System Prompt\n{system_prompt}\n\n### User Message\n{prompt}n\n### Assistant\n".replace('{prompt}', userMessagePrompt.replace('{prompt}', mockPrompt).replace('{fileContents}', mockFileContents)).replace('{system_prompt}', systemMessagePrompt),
  "request_type": "language-model-inference",
  "temperature": 0,
  "top_p": 0.7,
  "top_k": 50,
  "repetition_penalty": 1,
  "stream_tokens": false,
  "stop": [
    "</s>"
  ],
  "promptObj": {
    "prompt": ""
  }
}, {
  headers: {
    Authorization: 'Bearer 56a72f0d7e8da0e50634c291c60a21380a72d4cf167d3b3268e1d3e9b911b398'
  }    
}).then((response) => {
  console.log(response.data.choices[0]);
}, (error) => {
  console.log(error);
});