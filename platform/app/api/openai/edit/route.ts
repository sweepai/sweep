import { NextRequest, NextResponse } from "next/server"
import OpenAI from 'openai';


interface Body {
    fileContents: string
    prompt: string
}

const openai = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY || "", // This is the default and can be omitted
});

const systemMessagePrompt = `You are a brilliant and meticulous engineer assigned to modify a code file. When you write code, the code works on the first try and is syntactically perfect. You have the utmost care for the code that you write, so you do not make mistakes. Take into account the current code's language, code style and what the user is attempting to accomplish. You are to follow the instructions exactly and do nothing more. If the user requests multiple changes, you must make the changes one at a time and finish each change fully before moving onto the next change.

You MUST respond in the following diff format:

\`\`\`
<<<<<<< ORIGINAL
The first code block to replace. Ensure the indentation is valid.
=======
The new code block to replace the first code block. Ensure the indentation is valid.
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
The second code block to replace. Ensure the indentation is valid.
=======
The new code block to replace the second code block. Ensure the indentation is valid.
>>>>>>> MODIFIED
\`\`\`

You may write one or multiple diff hunks. DO NOT include extra lines of code. The MODIFIED can be empty.`

const userMessagePrompt = `Your job is to add modify the current code file in order to complete the user's request:
<user_request>
{prompt}
</user_request>

Here are the file's current contents:
<file_contents>
{fileContents}
</file_contents>`

// const codeBlockToExtendRegex = /<code_block_to_extend>([\s\S]*)<\/code_block_to_extend>/g
// const additionalUnitTestRegex = /<new_code>([\s\S]*)$/g

const diffRegex = /<<<<<<< ORIGINAL\n(?<oldCode>.*?)\n=======\n(?<newCode>.*?)\n>>>>>>> MODIFIED/gs

const countNumOccurences = (needle: string, haystack: string) => {
    if (needle === '') return 0;

    let count = 0;
    let pos = haystack.indexOf(needle);

    while (pos !== -1) {
        count++;
        pos = haystack.indexOf(needle, pos + 1);
    }

    return count;
}

const findMaximalSuffixMatch = (needle: string, haystack: string) => {
    const lines = needle.split("\n")
    for (var i = 0; i < lines.length; i += 1) {
        const substring = lines.slice(i).join("\n");
        if (countNumOccurences(substring, haystack) === 1) {
            return substring;
        }
    }
    return "";
}


const appendUnitTests = (oldCode: string, searchCode: string, appendCode: string) => {
    // if (searchCode && appendCode) {
    //     let codeBlockToExtend = searchCode[0];
    //     codeBlockToExtend = codeBlockToExtend.split('\n').slice(2, -2).join('\n');
    //     let additionalUnitTest = appendCode[0];
    //     additionalUnitTest = additionalUnitTest.split('\n').slice(2, -2).join('\n');
    //     console.log(codeBlockToExtend)
    //     console.log(additionalUnitTest)
        const maximalMatch = findMaximalSuffixMatch(searchCode, oldCode);
        return oldCode.replace(maximalMatch, maximalMatch + '\n\n' + appendCode);
    // } else {
    //     return "";
    // }
}

const callOpenAI = async (prompt: string, fileContents: string) => {
    const params: OpenAI.Chat.ChatCompletionCreateParams = {
        messages: [
            { role: 'user', content: systemMessagePrompt},
            { role: 'system', content: userMessagePrompt.replace('{prompt}', prompt).replace('{fileContents}', fileContents) }
        ],
        model: 'gpt-4-1106-preview',
    };
    const chatCompletion: OpenAI.Chat.ChatCompletion = await openai.chat.completions.create(params);
    const response = chatCompletion.choices[0].message.content!;
    console.log("file contents:\n", fileContents, "\n")
    console.log("response:\n", response, "\nend of response\n")
    const diffMatches = response.matchAll(diffRegex)!;
    if (!diffMatches) {
        return "";
    }
    var currentFileContents = fileContents;
    let it = 0
    console.log("inital currentFileContents:\n", currentFileContents, "\n")
    // @ts-ignore
    for (const diffMatch of diffMatches) {
        it += 1
        const oldCode = diffMatch.groups!.oldCode;
        const newCode = diffMatch.groups!.newCode;
        console.log("old code", oldCode, "\n")
        console.log("new code", newCode, "\n")
        currentFileContents = currentFileContents.replace(oldCode, newCode)
        // if (it < 3) {
        //     console.log("current file contents:\n", currentFileContents, "\n")
        // }

    }
    return currentFileContents
}

export async function POST(request: NextRequest) {
    const body = await request.json() as Body;
    console.log("body after being extracted in post request:", body)
    const response = await callOpenAI(body.prompt, body.fileContents);
    console.log(response)

    return NextResponse.json({
        newFileContents: response
    })
}

let mockFileContents = String.raw`
file contents import unittest
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

// const mockResponse = String.raw`
// <<<<<<< ORIGINAL
// class TestDiff(unittest.TestCase):
// =======
// class TestWhitespaceReversion(unittest.TestCase):
//     def test_revert_whitespace_changes(self):
//         print("Testing whitespace reversion with additional spaces")
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//     def test_revert_whitespace_changes(self):
// =======
//     def test_revert_whitespace_changes_more_whitespace(self):
//         print("Testing whitespace reversion with more whitespace in modified file")
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//     def test_revert_whitespace_changes_more_whitespace(self):
// =======
//     def test_revert_whitespace_changes_non_whitespace_changes(self):
//         print("Testing whitespace reversion ignoring non-whitespace changes")
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//     def test_revert_whitespace_changes_non_whitespace_changes(self):
// =======
//     def test_revert_whitespace_changes_same_files(self):
//         print("Testing whitespace reversion with identical original and modified files")
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//     def test_revert_whitespace_changes_same_files(self):
// =======
//     def test_revert_whitespace_changes_empty_files(self):
//         print("Testing whitespace reversion with empty files")
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//     def test_revert_whitespace_changes_empty_files(self):
// =======
//     def test_revert_whitespace_changes_whitespace_only_files(self):
//         print("Testing whitespace reversion with files that contain only whitespace")
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//     def test_revert_whitespace_changes_whitespace_only_files(self):
// =======
//     def test_format_contents(self):
//         print("Testing formatting of file contents")
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//     def test_format_contents(self):
// =======
//     @patch("sweepai.utils.diff.find_best_match")
//     def test_match_string(self, mock_find_best_match):
//         print("Testing string matching with mock")
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//     @patch("sweepai.utils.diff.find_best_match")
//     def test_match_string(self, mock_find_best_match):
// =======
//     def test_is_markdown(self):
//         print("Testing if file extension is markdown")
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//     def test_is_markdown(self):
// =======
// # No modifications required for this block.
// >>>>>>> MODIFIED
// `
