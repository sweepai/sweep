import copy
from math import inf
import os
import re
import sys

from rapidfuzz import fuzz, process
import stringzilla as sz

from loguru import logger
import rapidfuzz
from tqdm import tqdm
from sweepai.core.chat import ChatGPT, parse_function_calls_for_openai
from sweepai.core.entities import FileChangeRequest, Message
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.diff import generate_diff
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.modify_utils import manual_code_check
from sweepai.utils.utils import get_check_results


modify_tools_openai = """
# make_change - Make a SINGLE, TARGETED code change in a file. Preserve whitespace, comments, and style. Changes should be minimal, self-contained, and address only one specific modification. If a change affects multiple separate code sections, use multiple calls to this tool, one for each section.
To call this tool you must respond in the following xml format:

<make_change>
<justification>
Explain how this SINGLE change contributes to fulfilling the user's request.
</justification>
<file_name>
Name of the file where the change will be made. Ensure correct spelling as this is case-sensitive.
</file_name>
<original_code>
The existing lines of code that need modification or replacement. This should be a SINGLE, CONTINUOUS block of code, not multiple separate sections. Include unchanged surrounding lines for context. This CAN NOT be empty.
</original_code>
<new_code>
The new lines of code to replace the original code, implementing the SINGLE desired change. If the change is complex, break it into smaller targeted changes and use separate make_change calls for each.
</new_code>
</make_change>

# create_file - Create a new code file in the specified location with the given file name and extension. This is useful when the task requires adding entirely new functionality or classes to the codebase.
To call this tool you must respond in the following xml format:
<create_file>
<file_path>
The path where the new file should be created, relative to the root of the codebase. Do not include the file name itself.
</file_path>
<file_name>
he name to give the new file, including the extension. Ensure the name is clear, descriptive, and follows existing naming conventions.
</file_name>
<contents>
The initial contents of the new file.
</contents>
<justification>
Explain why creating this new file is necessary to complete the task and how it integrates with the existing codebase structure.
</justification>
</create_file>

# submit_result - Indicate that the task is complete and all requirements have been met. Provide the final code changes or solution.
To call this tool you must respond in the following xml format:
<submit_result>
<justification>
Summarize the code changes made and explain how they fulfill the user's original request. Provide the complete, modified code if applicable.
</justification>
</submit_result>"""

modify_tools = """<tool_description>
<tool_name>make_change</tool_name>
<description>
Make a SINGLE, TARGETED code change in a file. Preserve whitespace, comments, and style. Changes should be minimal, self-contained, and address only one specific modification. If a change affects multiple separate code sections, use this tool for one change at a time, one for each section.
</description>
<parameters>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Explain how this SINGLE change contributes to fulfilling the user's request.
</description>
</parameter>
<parameter>
<name>file_name</name>
<type>str</type>
<description>
Name of the file where the change will be made. Ensure correct spelling as this is case-sensitive.
</description>
</parameter>
<parameter>
<name>original_code</name>
<type>str</type>
<description>
The existing lines of code that need modification or replacement. This should be a short SINGLE, CONTINUOUS block of code, not multiple separate sections. Include unchanged surrounding lines for context. This CAN NOT be empty.
</description>
</parameter>
<parameter>
<name>new_code</name>
<type>str</type>
<description>
The new lines of code to replace the original code, implementing the SINGLE desired change. If the change is complex, break it into smaller targeted changes and use separate make_change calls for each.
</description>
</parameter>
<parameter>
<name>append</name>
<type>bool</type>
<description>
Optional: either true or false. If true, the new code will be appended to the original code. If false, the original code will be replaced by the new code. Use this to add new methods or test cases. Default is false.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>create_file</tool_name>
<description>
Create a new code file in the specified location with the given file name and extension. This is useful when the task requires adding entirely new functionality or classes to the codebase.
</description>
<parameters>
<parameter>
<name>file_path</name>
<type>str</type>
<description>
The path where the new file should be created, relative to the root of the codebase. Do not include the file name itself.
</description>
</parameter>
<parameter>
<name>file_name</name>
<type>str</type>
<description>
The name to give the new file, including the extension. Ensure the name is clear, descriptive, and follows existing naming conventions.
</description>
</parameter>
<parameter>
<name>contents</name>
<type>str</type>
<description>
The initial contents of the new file.
</description>
</parameter>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Explain why creating this new file is necessary to complete the task and how it integrates with the existing codebase structure.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>submit_task</tool_name>
<description>
Indicate that the current task is complete.
</description>
<parameters>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Summarize the code changes made and explain how they fulfill the user's original request.
</description>
</parameter>
</parameters>
</tool_description>"""

instructions = """You are an expert software developer tasked with editing code to fulfill the user's request. Your goal is to make the necessary changes to the codebase while following best practices and respecting existing conventions. 

To complete the task, follow these steps:

1. If new functionality is required that doesn't fit into existing files, create a new file with an appropriate name and location.

2. Make the code changes in a targeted way:
    - Preserve existing whitespace, comments and code style
    - Make surgical edits to only the required lines of code
    - If a change is complex, break it into smaller incremental changes
    - Ensure each change is complete and functional before moving on
        When providing code snippets, be extremely precise with indentation:
        - Count the exact number of spaces used for indentation
        - If tabs are used, specify that explicitly 
        - Ensure the indentation of the code snippet matches the original file exactly
3. After making all the changes, review the modified code to verify it fully satisfies the original request.
4. Once you are confident the task is complete, submit the final solution.

In this environment, you have access to the following tools to assist in fulfilling the user request:

You MUST call them like this:
<function_call>
<invoke>
<tool_name>$TOOL_NAME</tool_name>
<parameters>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</parameters>
</invoke>
</function_call>

Here are the tools available:

"""

NO_TOOL_CALL_PROMPT = """FAILURE
No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:

<function_call>
<invoke>
<tool_name>tool_name</tool_name>
<parameters>
<param_name>param_value</param_name>
</parameters>
</invoke>
</function_call>

Here is an example:

<function_call>
<invoke>
<tool_name>submit_task</tool_name>
<parameters>
<justification>The justification for making this change goes here.</justification>
</parameters>
</invoke>
</function_call>

If the current task is complete, call the submit_task function."""

NO_TOOL_CALL_PROMPT_OPENAI = """FAILURE
No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:

<function_call>
<tool_name>
<parameter1>
parameter1 value here
</parameter1>
<parameter2>
parameter2 value here
</parameter2>
</tool_name>
</function_call>

Here is an example:

<function_call>
<make_change>
<justification>
The justification for making this change goes here
</justification>
<file_name>
example-file.file
</file_name>
<original_code>
old code line here
</original_code>
<new_code>
new code line here
</new_code>
</make_change>
</function_call>

If the current task is complete, call the submit_task function.
"""

EMPTY_ORIGINAL_CODE_PROMPT = """The original_code variable is empty. It MUST contain a valid section of code from the existing file that you want to modify.

It seems like you are trying to use the make_change function to append code, you must follow these steps:

# 1. Thinking
<thinking>
a. Identify the code we are trying to append.
b. List function headers in this file that are relevant to the code we are trying to append, and explain what they each do. For example, if our code is tests multiplication, focus on tests that test multiplication. Follow this format:
    - Function: [function_name] - [description]
    [additional functions]
c. Identify the function you want to append the new_code block to, copying them completely and VERBATIM from the file. Do NOT paraphrase or abbreviate the source code, keeping all comments, docstrings, indentation, and whitespace. Placeholder comments like "# existing code" are not permitted. Be sure to copy the ENTIRE function or section of code. 
```
The function or section of code you want to append to.
```
d. Copy the new code you want to append with indentation matching that of the original_code block.
```
The new code you want to append.
```
</thinking>

# 2. Function call
Then generate a make_change function call with the following parameters:
a. Put the code from section c into the original_code variable.
b. Copy the code from original_code and paste it into the new_code variable.
c. Append the new code you want to add after the original code in the new_code variable.
d. Add the <append>true</append> flag. This is critical to ensure the new code is ADDED after the original code, instead of replacing the code.

Here's an illustrative example of how to use the make_change function to append code:

<example>
Here's an example of the input file:
<input>
<file_to_modify filename="tests/calculator_test.py">
import unittest
from calculator import Calculator

class TestAddition(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_add_positive_numbers(self):
        result = self.calc.add(2, 3)
        self.assertEqual(result, 5)

    def test_add_negative_numbers(self):
        result = self.calc.add(-2, -3)
        self.assertEqual(result, -5)

    def test_add_zero(self):
        result = self.calc.add(0, 0)
        self.assertEqual(result, 0)

class TestSubtraction(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_subtract_positive_numbers(self):
        result = self.calc.subtract(5, 3)
        self.assertEqual(result, 2)

    def test_subtract_negative_numbers(self):
        result = self.calc.subtract(-5, -3)
        self.assertEqual(result, -2)

    def test_subtract_zero(self):
        result = self.calc.subtract(5, 0)
        self.assertEqual(result, 5)

class TestMultiplication(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_multiply_positive_numbers(self):
        result = self.calc.multiply(2, 3)
        self.assertEqual(result, 6)

    def test_multiply_negative_numbers(self):
        result = self.calc.multiply(-2, 3)
        self.assertEqual(result, -6)

    def test_multiply_by_zero(self):
        result = self.calc.multiply(5, 0)
        self.assertEqual(result, 0)
</file_to_modify>
</input>

<thinking>
a. We are adding a new test case for multiplying two negative numbers in the calculator_test.py file.
b. List of relevant functions:
    - Function: test_multiply_positive_numbers - Tests multiplying positive numbers
    - Function: test_multiply_negative_numbers - Tests multiplying negative numbers
    - Function: test_multiply_by_zero - Tests multiplying by zero

c. Since we are adding a test case for multiplying two negative numbers, we should append the new test case right after the test_multiply_negative_numbers test. Here is the function we want to append to:
```
    def test_multiply_negative_numbers(self):
        result = self.calc.multiply(-2, 3)
        self.assertEqual(result, -6)
```
d. Here is the new test case we want to append with matching indentation:
```
    def test_multiply_negative_by_negative(self):
        result = self.calc.multiply(-4, -2)
        self.assertEqual(result, 8)
```
</thinking>

<function_call>
<make_change>
<justification>
Add a test case for multiplying a negative number by a negative number right after the test_multiply_negative_numbers test.
</justification>
<file_name>tests/calculator_test.py</file_name>
<original_code>
    def test_multiply_positive_numbers(self):
        result = self.calc.multiply(2, 3)
        self.assertEqual(result, 6)

    def test_multiply_negative_numbers(self):
        result = self.calc.multiply(-2, 3)
        self.assertEqual(result, -6)
</original_code>
<new_code>
    def test_multiply_negative_by_negative(self):
        result = self.calc.multiply(-4, -2)
        self.assertEqual(result, 8)
</new_code>
<append>true</append>
</make_change>
</function_call>
</example>

Notice how:
a. The original_code block is copied exactly from the existing code.
b. The original_code block consists of the functions we want to append the new code after.
c. Only a several lines of code are included before where you want to add the new code in the original_code block, but enough code is provided to give context.
d. The indentation in both original_code and new_code matches the file_to_modify code.
e. There are no placeholder comments like "# existing code" in the original_code block.

This is how you should append code using the make_change function. Please make another make_change function call with the corrected, non-empty <original_code> block and append flag set to true."""

DID_YOU_MEAN_PROMPT = """Fix your make_change function call by following these steps:

# 1. Thinking
<thinking>
Describe in great detail how your original_code block differs from what's in the codebase. Are you missing any indentation?
</thinking>

# 2. Function call
Make the make_change function call again, this time ensuring that the original_code parameter matches the code from file."""

self_review_prompt = """Before proceeding, it is important to review and critique the changes you have made. Follow these steps:

a. Review CURRENT TASK for requirements.
b. Analyze code patch:
    - Incorrect indentations that does not match surrounding code
    - Unnecessary deletions
    - Logic errors
    - Unhandled edge cases
    - Missing imports
    - Incomplete changes
    - Usage of nullable attributes
    - Non-functional code
    - Misalignment with plan and requirements
c. Perform critical contextual analysis:
    - Break down changes 
    - Explain reasoning
    - Identify logic issues, edge cases, plan deviations
    - Consider all scenarios and pitfalls
    - Consider backwards compatibility and future-proofing
    - Suggest fixes for problems
    - Evaluate error handling and fallback mechanisms
d. Be extremely critical. Do not overlook ANY issues.
e. Finally decide whether additional changes are needed or if the task is complete.

If additional changes are needed, make the necessary changes and call the make_change function again. If the task is complete, call the submit_task function."""

linter_warning_prompt = """There is a linter warning in the code changes. Resolve the warnings by following these steps:

# Thinking
<thinking>
a. Look closely at the changes made to identify any syntax errors that may have caused the linter errors. Does the number of indents in the changed code compare to the number of indents in the surrounding code?
b. Critique the change(s) you have made for any potential logical errors.
c. Identify what the linter warning is, and what may be causing it. Keep in mind that the actual cause of the error may be different from what the linter is suggesting, such as inconsistent indentation.
d. Indicate the minimum amount of changes required to resolve the linter warning.
</thinking>

Then, call the make_change function to fix the linter warnings. If the warning cannot be resolved, call submit_task with an explanation of the issue."""

fix_syntax_prompt = """You MUST resolve the issue by following these steps:

# 1. Thinking
<thinking>
a. Indicate what you have changed. Indicate the code that you have removed and the code that you have added back.
b. Identify where the broken code occurs and why it is broken.
c. Identify whether it is the code removed (original_code) that is causing the issue or the code added back (new_code).
d. Explain how we can correct the original_code or new_code in the make_change function call to create a correct change.
</thinking>

# 2. Function call
Then, reinvoke the make_change function call with different changes that yields valid code."""

ORIGINAL_CODE_NOT_FOUND_PROMPT = """The original_code provided does not appear to be present in file {file_path}. Your provided original_code erroneously contains:
```
{original_code}
```

Let's fix this error by responding in the following format:

# Thinking
<thinking>
1. List function headers in this file that are relevant to the code we are trying to append, and explain what they each do. For example, if our code is tests multiplication, focus on tests that test multiplication. Follow this format:
    - Function: [function_name] - [description]
    [additional functions]
Based on these options, deterimine the most similar function header to the original_code you provided.

2. Copy the most similar section of code from the ACTUAL contents of {file_path}. Follow this format:
```
ACTUAL contents of {file_path} that are most similar to original_code
```

3. Copy the most similar section of the ACTUAL contents of {file_path} to the previous <original_code>. This will go into the <original_code> parameter of the new function call. Follow this format:
```
The most similar section of the ACTUAL contents of {file_path}
```

4. Write the updated code, applying the changes from your previously provided <new_code> section into the new <original_code> parameter. This will go into the new <new_code> parameter.
</thinking>

# Function call
Then, follow up with a make_change function call with the corrected parameters. If you are unable to find the correct section of code, call the submit_task function with an explanation of the issue."""

MULTIPLE_OCCURRENCES_PROMPT = """You MUST resolve this error by following these steps:

# 1. Thinking
<thinking>
a. Identify whether you want to replace all occurrences of the original code or only a specific one. If you want to replace all occurrences, you can use the replace_all flag by adding <replace_all>true</replace_all> to the function arguments.
b. If you want to replace only a specific occurrence, which occurrence you want to replace and the corresponding surrounding context, following this format:

Corrected original code:
```
The original_code block you want to replace with surrounding context.
```

Corrected new code:
```
The new_code block you want to replace with the same surrounding context.
```
</thinking>

# 2. Function Call
Then, call the make_change function again with either the replace_all flag or additional context in the original_code block to specify which occurrence you want to replace."""

tool_call_parameters = {
    "make_change": ["justification", "file_name", "original_code", "new_code"],
    "create_file": ["justification", "file_name", "file_path", "contents"],
    "submit_task": ["justification"],
}

DEFAULT_FUNCTION_CALL = """<function_call>
<invoke>
<tool_name>make_change</tool_name>
<parameters>
<justification>
{justification}
</justification>
<file_name>
{file_path}
</file_name>
<original_code>
{original_code}
</original_code>
<new_code>
{new_code}
</new_code>{flags}
</parameters>
</invoke>
</function_call>"""

SUBMIT_TASK_MOCK_FUNCTION_CALL = """<function_call>
<invoke>
<tool_name>submit_task</tool_name>
<parameters>
<justification>
{justification}
</justification>
</parameters>
</invoke>
</function_call>"""

def english_join(items: list[str]) -> str:
    if len(items) == 0:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"

def rstrip_lines(text: str) -> str:
    """Claude likes to put trailing spaces at the end of lines. This function removes them."""
    return "\n".join([line.rstrip() for line in text.split("\n")])

def indent(text: str, spaces: int) -> str:
    return "\n".join([f"{' ' * spaces}{line}" if line.strip() else "" for line in text.split("\n")])

def tokenize_code(code: str):
    cleaned_code = ""
    for line in code.split("\n"):
        stripped_line = line.strip()
        if stripped_line.startswith("#") or stripped_line.startswith("//") or len(stripped_line) == 0:
            continue
        cleaned_code += line + "\n"
    return [str(token) for token in sz.Str(cleaned_code).split_charset(separator=' \n\t\r()\{\}\[\]', maxsplit=sys.maxsize, keepseparator=True) if str(token).strip()]

def code_processor(code: str):
    return " ".join(tokenize_code(code))

def find_best_matches(
    needle: str,
    haystack: str,
    threshold: int = 50,
    verbose=True,
    num_matches=5,
    tokenized=False,
    **kwargs
):
    best_matches = []
    file_contents_lines = haystack.split("\n")
    num_lines = len(file_contents_lines)
    num_non_whitespace_chars = sum([not char.isspace() for char in needle])
    max_char_diff = 300
    for start_line in tqdm(range(num_lines), total=num_lines) if verbose else range(num_lines):
        potential_choices = []
        end_lines = []
        end_line = start_line
        current_string = ""
        num_chars = 0
        while num_chars < num_non_whitespace_chars + max_char_diff and end_line < num_lines:
            current_string += file_contents_lines[end_line] + "\n"
            num_chars += sum([not char.isspace() for char in file_contents_lines[end_line]])
            end_line += 1
            if num_chars > num_non_whitespace_chars - max_char_diff:
                potential_choices.append(current_string.rstrip('\n'))
                end_lines.append(end_line)

        # This can deadlock somehow
        results = process.extract(
            needle,
            potential_choices,
            scorer=fuzz.QRatio, 
            score_cutoff=threshold, 
            limit=num_matches,
            processor=tokenize_code if tokenized else None,
            **kwargs
        )

        for _choice, score, index in results:
            if score >= threshold:
                best_matches.append((score, (potential_choices[index], start_line, end_lines[index])))
        best_matches = sorted(best_matches, key=lambda x: x[0], reverse=True)[:num_matches]
    
    deduped_best_matches = []
    covered_spans = set()
    for score, (match, start_line, end_line) in best_matches:
        if set(range(start_line, end_line)) & covered_spans:
            continue
        covered_spans |= set(range(start_line, end_line))
        deduped_best_matches.append((match, score))
    return deduped_best_matches[:num_matches]

def find_best_match(*args, **kwargs):
    results = find_best_matches(*args, **kwargs)
    if len(results) > 0:
        return results[0]
    return "", 0

def find_max_indentation(needle: str):
    max_indent = 0
    for line in needle.splitlines():
        if len(line) == 0:
            continue
        max_indent = max(max_indent, len(line) - len(line.lstrip()))
    return max_indent

def contains_ignoring_whitespace(needle: str, haystack: str):
    needle = "\n".join([line.rstrip() for line in needle.splitlines()])
    haystack = "\n".join([line.rstrip() for line in haystack.splitlines()])
    max_indent = find_max_indentation(needle)
    for indent_size in range(0, max_indent + 2, 2):
        indented_needle = indent(needle, indent_size)
        if indented_needle in haystack:
            start_char = haystack.index(indented_needle)
            start_line = haystack[:start_char].count("\n")
            end_line = start_line + indented_needle.count("\n") + 1
            return start_line, end_line
    return False

MODEL = "claude-3-haiku-20240307"
SLOW_MODEL = "claude-3-opus-20240229"

def validate_and_parse_function_call_openai(
    function_calls_string: str, chat_gpt: ChatGPT
) -> list[AnthropicFunctionCall]:
    function_calls = parse_function_calls_for_openai(
        function_calls_string.strip("\n") + "\n</function_call>"
    )
    if len(function_calls) > 0:
        function_calls[0] = AnthropicFunctionCall(
            function_name=function_calls[0]['tool'],
            function_parameters=function_calls[0]['arguments'],
        )
        if "<function_call>" in function_calls_string:
            chat_gpt.messages[-1].content = (
                chat_gpt.messages[-1].content.rstrip("\n") + "\n</function_call>"
            )
    return function_calls[0] if len(function_calls) > 0 else None


def validate_and_parse_function_call(
    function_calls_string: str, chat_gpt: ChatGPT
) -> AnthropicFunctionCall:
    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n") + "\n</function_call>"
    )  # add end tag
    if len(function_calls) > 0:
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</function_call>"
        )  # add end tag to assistant message
        return function_calls[0] if len(function_calls) > 0 else None

    # try adding </invoke> tag as well
    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n") + "\n</invoke>\n</function_call>"
    )
    if len(function_calls) > 0:
        # update state of chat_gpt
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</invoke>\n</function_call>"
        )
        return function_calls[0] if len(function_calls) > 0 else None
    # try adding </parameters> tag as well
    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n")
        + "\n</parameters>\n</invoke>\n</function_call>"
    )
    if len(function_calls) > 0:
        # update state of chat_gpt
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n")
            + "\n</parameters>\n</invoke>\n</function_call>"
        )
    return function_calls[0] if len(function_calls) > 0 else None

def create_user_message( # TODO: has non-deterministic behavior
        fcrs: list[FileChangeRequest],
        request: str,
        cloned_repo: ClonedRepo,
        relevant_filepaths: list[str] = None,
        modify_files_dict: dict[str, dict[str, str]] = None
    ) -> str:
    current_fcr_index = [i for i, fcr in enumerate(fcrs) if not fcr.is_completed][0] if any([not fcr.is_completed for fcr in fcrs]) else 0
    combined_request_unformatted = "{relevant_files}# Plan of Code Changes\n\nIn order to solve the user's request you will need to modify or create {files_to_modify_list}.{completed_prompt} Here are the instructions for the edits you need to make:\n\n<files_to_change>\n{files_to_modify}\n</files_to_change>"
    completed_prompt = "" if current_fcr_index == 0 else f" You have already completed {current_fcr_index} of the {len(fcrs)} required changes."
    if modify_files_dict:
        combined_request_unformatted += "\nThe above files reflect the latest updates you have already made. READ THROUGH THEM CAREFULLY TO FIGURE OUT WHAT YOUR NEXT STEPS ARE. Call the make_change, create_file or submit_task tools."
    files_to_modify_string = ""

    files_to_modify_messages = {fcr.filename: "" for fcr in fcrs}
    for i, fcr in enumerate(fcrs):
        # first add the instructions to the user message
        if i < current_fcr_index: # already done
            files_to_modify_messages[fcr.filename] += f"\n\nYou have already {past_tense_mapping[fcr.change_type]} {fcr.filename}, where the specific instructions were to:\n\n{fcr.instructions}"
        elif i == current_fcr_index:
            files_to_modify_messages[fcr.filename] += f"\n\nYour current task is to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n{fcr.instructions}"
        else:
            files_to_modify_messages[fcr.filename] += f"\n\nYou will later need to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n{fcr.instructions}"
        # now add the contents of the file to the user message
        # only add the contents if this is the last fcr for the filename
        last_occurence = i
        # loop from current index to end of fcrs to see if this fcr is the last time the filename shows up
        for j in range(i + 1, len(fcrs)):
            if fcrs[j].filename == fcr.filename:
                last_occurence = j
        if last_occurence == i:
            if fcr.change_type == "modify":
                if not modify_files_dict:
                    files_to_modify_messages[fcr.filename] += f"\n\n<file_to_modify filename=\"{fcr.filename}\">\n{cloned_repo.get_file_contents(file_path=fcr.filename)}\n</file_to_modify>"
                else: # show the latest contents of the file
                    latest_file_contents = get_latest_contents(fcr.filename, cloned_repo, modify_files_dict)
                    files_to_modify_messages[fcr.filename] += f"\n\n<file_to_modify filename=\"{fcr.filename}\">\n{latest_file_contents}\n</file_to_modify>"
            elif fcr.change_type == "create":
                files_to_modify_messages[fcr.filename] += f"\n<file_to_create filename=\"{fcr.filename}\">\n{fcr.instructions}\n</file_to_create>"
    # now we combine the messages into a single string
    already_added_files = set([])
    for fcr in fcrs[::-1]:
        if fcr.filename in already_added_files:
            continue
        files_to_modify_string += files_to_modify_messages[fcr.filename]
        already_added_files.add(fcr.filename)

    deduped_file_names = []
    for fcr in fcrs:
        if fcr.filename not in deduped_file_names:
            deduped_file_names.append(fcr.filename)
    combined_request_message = combined_request_unformatted \
        .replace("{files_to_modify}", files_to_modify_string.lstrip('\n')) \
        .replace("{files_to_modify_list}", english_join(deduped_file_names)) \
        .replace("{completed_prompt}", completed_prompt)
    precomputed_file_list = cloned_repo.get_file_list()
    if relevant_filepaths:
        relevant_file_paths_string = ""
        for relevant_file_path in relevant_filepaths:
            if relevant_file_path not in precomputed_file_list:
                logger.warning(f"Relevant file path {relevant_file_path} not found in cloned repo.") # the relevant file paths aren't well formatted, so we get some issues here
                continue
            if relevant_file_path in [fcr.filename for fcr in fcrs]:
                logger.warning(f"Relevant file path {relevant_file_path} is already in the list of files to modify.")
                continue
            relevant_file_paths_string += f"\n\n<relevant_module filename=\"{relevant_file_path}\">\n{cloned_repo.get_file_contents(file_path=relevant_file_path)}\n</relevant_module>"
        relevant_file_paths_string = f"<relevant_files>\n{relevant_file_paths_string}\n</relevant_files>"
        combined_request_message = combined_request_message.replace("{relevant_files}", f'\nHere are some relevant modules, such as useful helper functions for resolving this issue. You likely will not need to edit these modules but may need to import them or understand their usage interface: {relevant_file_paths_string}\n')
    else:
        combined_request_message = combined_request_message.replace("{relevant_files}", "")
    user_message = f"<user_request>\n{request}\n</user_request>\n{combined_request_message}"
    return user_message

# find out if any changes were made by matching the contents of the files
def changes_made(modify_files_dict: dict[str, dict[str, str]], previous_modify_files_dict) -> bool:
    # check if there are any changes made
    for file_name, file_data in modify_files_dict.items():
        if file_name not in previous_modify_files_dict:
            if file_data['contents'] != file_data["original_contents"]:
                return True
            else:
                continue
        if file_data['contents'] != previous_modify_files_dict[file_name]['contents']:
            return True
    return False

past_tense_mapping = {
    "modify": "modified",
    "create": "created",
}

# Magic
def ordinal(n: int):
    return "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4]) # noqa

def render_plan(fcrs: list[FileChangeRequest]) -> str:
    current_fcr_index = [i for i, fcr in enumerate(fcrs) if not fcr.is_completed][0] if any([not fcr.is_completed for fcr in fcrs]) else 0
    plan = f"You have {len(fcrs)} changes to make and you are currently working on the {ordinal(current_fcr_index + 1)} task."
    for i, fcr in enumerate(fcrs):
        if i < current_fcr_index:
            plan += f"\n\nTask {i}: You have previously {past_tense_mapping[fcr.change_type]} {fcr.filename}, where you were asked to:\n\n{fcr.instructions}"
        elif i == current_fcr_index:
            plan += f"\n\nTask {i}: Your CURRENT TASK is to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n{fcr.instructions}"
        else:
            plan += f"\n\nTask {i}: You will later need to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n{fcr.instructions}"
    return plan.strip('\n')

# get current task being worked on
def get_current_task_index(fcrs: list[FileChangeRequest]) -> str:
    current_fcr_index = 0
    for current_fcr_index, fcr in enumerate(fcrs):
        if not fcr.is_completed:
            break
    return current_fcr_index

def render_current_task(fcrs: list[FileChangeRequest]) -> str:
    current_fcr_index = 0
    for current_fcr_index, fcr in enumerate(fcrs):
        if not fcr.is_completed:
            break
    fcr = fcrs[current_fcr_index]
    return f"The CURRENT TASK is to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n<current_task>\n{fcr.instructions}\n</current_task>"

# return replaces per fcr, -1 if there are any issues
def get_replaces_per_fcr(fcr: FileChangeRequest) -> int:
    original_code_pattern = r"<original_code>(.*?)</original_code>"
    new_code_pattern = r"<new_code>(.*?)</new_code>"
    original_code_matches = list(re.finditer(original_code_pattern, fcr.instructions, re.DOTALL))
    new_code_matches = list(re.finditer(new_code_pattern, fcr.instructions, re.DOTALL))
    if len(original_code_matches) != len(new_code_matches):
        logger.error(f"Mismatched old/new code sections in fcr! {len(original_code_matches)} to {len(new_code_matches)}")
        return -1
    return len(original_code_matches)

def parse_fcr(fcr: FileChangeRequest):
    flags = ""
    justification, *_ = fcr.instructions.split("<original_code>", 1)
    original_code_pattern = r"<original_code>\s*\n(.*?)</original_code>"
    new_code_pattern = r"<new_code>\s*\n(.*?)</new_code>"
    original_code_matches = list(re.finditer(original_code_pattern, fcr.instructions, re.DOTALL))
    new_code_matches = list(re.finditer(new_code_pattern, fcr.instructions, re.DOTALL))
    replace_all_pattern = r"<replace_all>true</replace_all>"
    replace_all_matches = list(re.finditer(replace_all_pattern, fcr.instructions, re.DOTALL))
    if replace_all_matches:
        flags += "\n<replace_all>true</replace_all>"
    return {
        "justification": justification.strip(),
        "file_path": fcr.filename,
        "original_code": [original_code_match.group(1).strip("\n") for original_code_match in original_code_matches],
        "new_code": [new_code_match.group(1).strip("\n") for new_code_match in new_code_matches],
        "replace_all": bool(replace_all_matches),
    }

# returns the old/new code change as a function call
def compile_fcr(fcr: FileChangeRequest, index: int) -> str:
    # justification is wrong, fix this later!
    parsed_fcr = parse_fcr(fcr)
    if parsed_fcr["replace_all"]:
        flags = "\n<replace_all>true</replace_all>"
    else:
        flags = ""
    return DEFAULT_FUNCTION_CALL.format(justification=parsed_fcr["justification"], file_path=parsed_fcr["file_path"], original_code=parsed_fcr["original_code"][index], new_code=parsed_fcr["new_code"][index], flags=flags)

# return the number of tasks completed
def tasks_completed(fcrs: list[FileChangeRequest]):
    completed_tasks = 0
    for fcr in fcrs:
        if fcr.is_completed:
            completed_tasks += 1
    return completed_tasks

def modify(
    fcrs: list[FileChangeRequest],
    request: str,
    cloned_repo: ClonedRepo,
    relevant_filepaths: list[str],
    chat_logger: ChatLogger | None = None,
    use_openai: bool = False,
    previous_modify_files_dict: dict[str, dict[str, str]] = {},
) -> dict[str, dict[str, str]]:
    # join fcr in case of duplicates
    if not fcrs:
        return previous_modify_files_dict
    user_message = create_user_message(
        fcrs=fcrs,
        request=request,
        cloned_repo=cloned_repo,
        relevant_filepaths=relevant_filepaths,
    )
    chat_gpt = ChatGPT()
    llm_state = {
        "initial_check_results": {},
        "done_counter": 0, # keep track of how many times the submit_task tool has been called
        "request": request,
        "plan": render_plan(fcrs), 
        "current_task": render_current_task(fcrs),
        "user_message_index": 1,  # used for detailed chat logger messages
        "user_message_index_chat_logger": 1,  # used for detailed chat logger messages
        "fcrs": fcrs,
        "previous_attempt": "",
        "changes_per_fcr": [get_replaces_per_fcr(fcr) for fcr in fcrs], # how many old/new code pairs there are per fcr
        "completed_changes_per_fcr": [0 for _ in fcrs], # how many successful changes have been applied per fcr
        "attempt_lazy_change": True, # whether or not we attempt to bypass the llm call and apply old/new code pair directly
        "attempt_count": 0, # how many times we have attempted to apply the old/new code pair
        "visited_set": set(), # keep track of which outputs have been attempted
    }
    full_instructions = instructions + (modify_tools_openai if use_openai else modify_tools)
    chat_gpt.messages = [Message(role="system", content=full_instructions)]
    try:
        compiled_fcr = compile_fcr(fcrs[0], 0)
        if compiled_fcr:
            chat_gpt.messages.append(Message(role="user", content=f"Here is the intial user request, plan, and state of the code files:\n{user_message}"))
            function_calls_string = compiled_fcr
            chat_gpt.messages.append(Message( # this will happen no matter what
                role="assistant",
                content=function_calls_string
            ))
            # update messages to make it seem as if it called the fcr
            # update state if it's bad
            # TODO: handling logic to be moved out
            function_call = validate_and_parse_function_call(function_calls_string, chat_gpt) # this will raise if it's bad but compile_fcr should guarantee it's good
            if function_call.function_parameters["original_code"] == function_call.function_parameters["new_code"]:
                current_fcr_index = get_current_task_index(llm_state["fcrs"])
                llm_state["completed_changes_per_fcr"][current_fcr_index] += 1
                for fcr in llm_state["fcrs"]:
                    if not fcr.is_completed:
                        fcr.is_completed = True # incrementing because we should skip bad calls
                        break
                llm_state["attempt_count"] = 0
                llm_state['current_task'] = render_current_task(llm_state["fcrs"]) # rerender the current task
                user_response = f"SUCCESS\n\nThe previous task is now complete. Please move on to the next task. {llm_state['current_task']}"
                llm_state["attempt_lazy_change"] = True
                llm_state["visited_set"] = set()
                function_calls_string = chat_gpt.chat_anthropic(
                    content=user_response,
                    stop_sequences=["</function_call>"],
                    model=MODEL,
                    message_key="user_request",
                    use_openai=use_openai,
                )
        else:
            model = MODEL
            logger.info(f"Using model: {model}")
            function_calls_string = chat_gpt.chat_anthropic(
                content=f"Here is the intial user request, plan, and state of the code files:\n{user_message}",
                stop_sequences=["</function_call>"],
                model=model,
                message_key="user_request",
                use_openai=use_openai,
            )
    except Exception as e:
        logger.error(f"Error in chat_anthropic: {e}")
        chat_logger.add_chat(
            {
                "model": chat_gpt.model,
                "messages": [{"role": message.role, "content": message.content} for message in chat_gpt.messages],
                "output": f"ERROR:\n{e}\nEND OF ERROR",
            })
        return {}
    if not previous_modify_files_dict:
        previous_modify_files_dict = {}
    modify_files_dict = copy.deepcopy(previous_modify_files_dict)
    # this message list is for the chat logger to have a detailed insight into why failures occur
    detailed_chat_logger_messages = [{"role": message.role, "content": message.content} for message in chat_gpt.messages]
    # used to determine if changes were made
    previous_modify_files_dict = copy.deepcopy(modify_files_dict)
    for i in range(len(fcrs) * 15):
        if use_openai:
            function_call = validate_and_parse_function_call_openai(function_calls_string, chat_gpt)
        else:
            function_call = validate_and_parse_function_call(function_calls_string, chat_gpt)
        if function_call:
            num_of_tasks_done = tasks_completed(fcrs)
            # note that detailed_chat_logger_messages is meant to be modified in place by handle_function_call
            function_output, modify_files_dict, llm_state = handle_function_call(cloned_repo, function_call, modify_files_dict, llm_state, chat_logger_messages=detailed_chat_logger_messages, use_openai=use_openai)
            fcrs = llm_state["fcrs"]
            if function_output == "DONE":
                # add the diff of all changes to chat_logger
                if chat_logger:
                    final_message = "DONE\nHere is a summary of all the files changed:\n\n"
                    for file_name, file_data in modify_files_dict.items():
                        file_diff = generate_diff(file_data['original_contents'], file_data['contents'])
                        if file_diff:
                            final_message += f"\nChanges made to {file_name}:\n{file_diff}"
                    chat_logger.add_chat({
                        "model": chat_gpt.model,
                        "messages": detailed_chat_logger_messages,
                        "output": f"{final_message}",
                    })
                break
            detailed_chat_logger_messages.append({"role": "user", "content": function_output})

            if modify_files_dict: # update the state of the LLM
                user_message = create_user_message(
                    fcrs=fcrs,
                    request=request,
                    cloned_repo=cloned_repo,
                    relevant_filepaths=relevant_filepaths,
                    modify_files_dict=modify_files_dict
                )
                user_message = f"Here is the UPDATED user request, plan, and state of the code changes. REVIEW THIS CAREFULLY!\n{user_message}"
                # state cleanup should only occur after a task has been finished and if a change was made and if a change was made
                current_num_of_tasks_done = tasks_completed(fcrs)
                if changes_made(modify_files_dict, previous_modify_files_dict) and current_num_of_tasks_done > num_of_tasks_done:
                    # remove the previous user message and add it to the end, do not remove if it is the inital user message
                    chat_gpt.messages = chat_gpt.messages[:1]
                    detailed_chat_logger_messages = detailed_chat_logger_messages[:1]
                    chat_gpt.messages.append(Message(role="user", content=user_message))
                    detailed_chat_logger_messages.append({"role": "user", "content": user_message})
                    # update the index
                    llm_state["user_message_index"] = len(chat_gpt.messages) - 1
                    llm_state["user_message_index_chat_logger"] = len(detailed_chat_logger_messages) - 1
                previous_modify_files_dict = copy.deepcopy(modify_files_dict)
        else:
            function_output = "FAILURE: No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:\n" \
                + "<function_call>\n<invoke>\n<tool_name>tool_name</tool_name>\n<parameters>\n<param_name>param_value</param_name>\n</parameters>\n</invoke>\n</function_call>"
        if chat_logger:
            if i == len(fcrs) * 10 - 1:
                chat_logger.add_chat(
                    {
                        "model": chat_gpt.model,
                        "messages": detailed_chat_logger_messages,
                        "output": f"WARNING We have reached the end the max amount of iterations: {i + 1}, but we have not finished with our changes yet!",
                    })
            else:
                chat_logger.add_chat(
                    {
                        "model": chat_gpt.model,
                        "messages": detailed_chat_logger_messages,
                        "output": detailed_chat_logger_messages[-1]["content"],
                    })
        try:
            function_calls_string = ""
            compiled_fcr = ""
            current_fcr_index = get_current_task_index(fcrs)
            change_in_fcr_index = llm_state["completed_changes_per_fcr"][current_fcr_index]
            max_changes = llm_state["changes_per_fcr"][current_fcr_index]
            lazy_change = llm_state["attempt_lazy_change"]
            # on first attempt of a new task we use the first fcr
            if change_in_fcr_index >= max_changes:
                function_calls_string = SUBMIT_TASK_MOCK_FUNCTION_CALL.format(justification=f"Task {current_fcr_index} is now complete.")
            else:
                if lazy_change:
                    compiled_fcr = compile_fcr(fcrs[current_fcr_index], change_in_fcr_index)
                    if compiled_fcr:
                        function_calls_string = compiled_fcr
                        function_call = validate_and_parse_function_call(function_calls_string, chat_gpt) # this will raise if it's bad but compile_fcr should guarantee it's good
                        if function_call.function_parameters["original_code"] == function_call.function_parameters["new_code"]:
                            current_fcr_index = get_current_task_index(llm_state["fcrs"])
                            llm_state["completed_changes_per_fcr"][current_fcr_index] += 1
                            for fcr in llm_state["fcrs"]:
                                if not fcr.is_completed:
                                    fcr.is_completed = True # incrementing because we should skip bad calls
                                    break
                            if all([fcr.is_completed for fcr in llm_state["fcrs"]]):
                                return modify_files_dict
                            llm_state["attempt_count"] = 0
                            llm_state['current_task'] = render_current_task(llm_state["fcrs"]) # rerender the current task
                            llm_state["attempt_lazy_change"] = True
                            llm_state["visited_set"] = set()
                            user_response = f"SUCCESS\n\nThe previous task is now complete. Please move on to the next task. {llm_state['current_task']}"
                            function_calls_string = chat_gpt.chat_anthropic(
                                content=user_response,
                                stop_sequences=["</function_call>"],
                                model=MODEL,
                                message_key="user_request",
                                use_openai=use_openai,
                            )
                        # update messages to make it seem as if it called the fcr
                        chat_gpt.messages.append(Message(
                            role="assistant",
                            content=function_calls_string
                        ))
                # if previous things go wrong we make llm call
                if not function_calls_string:
                    model = MODEL if llm_state["attempt_count"] < 3 else SLOW_MODEL
                    logger.info(f"Using model: {model}")
                    function_calls_string = chat_gpt.chat_anthropic(
                        content=function_output,
                        model=model,
                        stop_sequences=["</function_call>"],
                        use_openai=use_openai,
                    )
                    if function_calls_string in llm_state["visited_set"]:
                        if llm_state["attempt_count"] < 3:
                            logger.warning(f"Function call {function_calls_string} has already been visited, retrying with a different model.")
                            llm_state["attempt_count"] = 3
                            function_calls_string = chat_gpt.chat_anthropic(
                                content=SLOW_MODEL,
                                model=model,
                                stop_sequences=["</function_call>"],
                                use_openai=use_openai,
                            )
                            if function_calls_string in llm_state["visited_set"]:
                                logger.warning(f"Function call {function_calls_string} has already been visited, skipping task {current_fcr_index}.")
                                function_calls_string = SUBMIT_TASK_MOCK_FUNCTION_CALL.format(justification=f"Skipping task {current_fcr_index} due to too many retries.")
                            else:
                                llm_state["visited_set"] = set()
                        else:
                            logger.warning(f"Function call {function_calls_string} has already been visited, skipping task {current_fcr_index}.")
                            function_calls_string = SUBMIT_TASK_MOCK_FUNCTION_CALL.format(justification=f"Skipping task {current_fcr_index} due to too many retries.")
            detailed_chat_logger_messages.append({"role": "assistant", "content": function_calls_string})
        except Exception as e:
            logger.error(f"Error in chat_anthropic: {e}")
            with open("msg.txt", "w") as f:
                for message in chat_gpt.messages:
                    f.write(f"{message.content}\n\n")
            if chat_logger is not None:
                chat_logger.add_chat(
                    {
                        "model": chat_gpt.model,
                        "messages": detailed_chat_logger_messages,
                        "output": f"ERROR: AN ERROR OCCURED ON ITERATION {i + 1}:\n{e}\nEND OF ERROR",
                    })
            break
    else:
        logger.error("Max iterations reached")
        # breakpoint()
    diff_string = ""
    for file_name, file_data in modify_files_dict.items():
        diff = generate_diff(file_data['original_contents'], file_data['contents'])
        if diff:
            diff_string += f"\nChanges made to {file_name}:\n{diff}"
    return modify_files_dict


def generate_diffs(modify_files_dict: dict[str, dict[str, str]]) -> dict[str, str]:
    changes_made = False
    for file_name, file_data in modify_files_dict.items():
        new_contents = file_data["contents"]
        original_contents = file_data["original_contents"]
        diff = generate_diff(original_contents, new_contents)
        if diff:
            changes_made = True
    return changes_made

def generate_diff_string(modify_files_dict: dict[str, dict[str, str]]) -> dict[str, str]:
    diff_string = ""
    for file_name, file_data in modify_files_dict.items():
        new_contents = file_data["contents"]
        original_contents = file_data["original_contents"]
        diff_string += f"{file_name}\n{generate_diff(original_contents, new_contents)}\n"
    return diff_string

def create_tool_call_response(tool_name: str, tool_call_response_contents: str) -> str:
    return f"<function_results>\n<result>\n<tool_name>{tool_name}<tool_name>\n<stdout>\n{tool_call_response_contents}\n</stdout>\n</result>\n</function_results>"

def get_latest_contents(file_name: str, cloned_repo: ClonedRepo, modify_files_dict: dict) -> str:
    if file_name in modify_files_dict and "contents" in modify_files_dict[file_name]:
        return modify_files_dict[file_name]["contents"]
    elif file_name in cloned_repo.get_file_list():
        return cloned_repo.get_file_contents(file_name)
    else:
        return ""
    
def get_surrounding_lines(file_contents: str, best_match: str) -> tuple[str, str]:
    best_match_index = file_contents.find(best_match)
    NUM_LINES_SURROUNDING = 6
    surrounding_lines_before = "\n"
    surrounding_lines_after = ""
    if best_match_index != -1:
        # OPUS START - this is a hacky way to get the surrounding lines, doesn't handle inline \n
        # Find the index of the fifth \n before the best_match_index
        best_match_start = max(0, file_contents.rfind("\n", 0, best_match_index))
        for _ in range(NUM_LINES_SURROUNDING - 1):
            best_match_start = max(0, file_contents.rfind("\n", 0, best_match_start))

        # Find the index of the fifth \n after the best_match_index
        best_match_end = best_match_index + len(best_match)
        for _ in range(NUM_LINES_SURROUNDING * 2): # 2x the number of lines surrounding after for now
            best_match_end = file_contents.find("\n", best_match_end + 1)
            if best_match_end == -1:
                best_match_end = len(file_contents)
                break
        # OPUS END
        surrounding_lines_before = file_contents[best_match_start:best_match_index]
        surrounding_lines_after = file_contents[best_match_index:best_match_end]
    return surrounding_lines_before, surrounding_lines_after

def handle_function_call(
    cloned_repo: ClonedRepo,
    function_call: AnthropicFunctionCall,
    modify_files_dict: dict[str, dict[str, str]],
    llm_state: dict,
    chat_logger_messages: list[dict[str, str]] | None = None,
    use_openai: bool = False,
):
    # iterate through modify_files_dict and generate diffs
    llm_response = ""
    tool_name = function_call.function_name
    tool_call = function_call.function_parameters
    if tool_name == "submit_task":
        current_fcr_index = get_current_task_index(llm_state["fcrs"])
        llm_state["completed_changes_per_fcr"][current_fcr_index] += 1
        changes_made = generate_diffs(modify_files_dict)
        if changes_made:
            llm_response = "DONE"
        else:
            llm_state["done_counter"] += 1
            if llm_state["done_counter"] > 3:
                llm_response = "DONE"
            else:
                llm_response = "ERROR\n\nNo changes were made. Please continue working on your task."
        for fcr in llm_state["fcrs"]:
            if not fcr.is_completed:
                fcr.is_completed = True
                break
        llm_state["attempt_count"] = 0
        llm_state['current_task'] = render_current_task(llm_state["fcrs"]) # rerender the current task
        llm_response = f"SUCCESS\n\nThe previous task is now complete. Please move on to the next task. {llm_state['current_task']}"
        if all([fcr.is_completed for fcr in llm_state["fcrs"]]):
            llm_response = "DONE"
        llm_state["attempt_lazy_change"] = True
        llm_state["visited_set"] = set()
    elif tool_name == "no_tool_call":
        if use_openai:
            llm_response = NO_TOOL_CALL_PROMPT_OPENAI
        else:
            llm_response = NO_TOOL_CALL_PROMPT
    elif tool_name == "make_change":
        error_message = ""
        for key in ["file_name", "original_code", "new_code"]:
            if key not in tool_call:
                error_message += f"Missing {key} in tool call. Call the tool again but this time provide the {key}.\n"
                if key == "new_code" or key == "original_code":
                    error_message += "\n\nIt is likely the reason why you have missed these keys is because the original_code block you provided is WAY TOO LARGE and as such you have missed the closing xml tags. REDUCE the original_code block to be under 10 lines of code!"
        if not tool_call["original_code"].strip():
            error_message = EMPTY_ORIGINAL_CODE_PROMPT
        warning_message = ""
        if not error_message:
            for _ in range(1): # this is super jank code but it works for now - only for easier error message handling
                # ensure the file we are editting exists and is in modify_files_dict
                if "file_name" in tool_call:
                    file_name = tool_call["file_name"].strip()
                    # if not in codebase or has not been created
                    if not os.path.exists(os.path.join(cloned_repo.repo_dir, file_name)) and file_name not in modify_files_dict:
                        error_message += f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!\n"
                        break
                llm_state['initial_check_results'][file_name] = get_check_results(file_name, get_latest_contents(file_name, cloned_repo, modify_files_dict))
                success_message = ""
                original_code = tool_call["original_code"].strip("\n")
                new_code = tool_call["new_code"].strip("\n")
                if tool_call.get("append", "false").strip() == "true":
                    new_code = original_code + "\n\n" + new_code
                replace_all = tool_call.get("replace_all", "false").strip() == "true"
                # get the latest contents of the file
                file_contents = get_latest_contents(file_name, cloned_repo, modify_files_dict)
                # if the file is not in modify_files_dict, add it
                if file_name not in modify_files_dict:
                    modify_files_dict[file_name] = {"contents": file_contents, "original_contents": file_contents}
                warning_message = ""
                
                # handle special case where there are \r\n characters in the current chunk as this will cause search and replace to ALWAYS fail
                if "\r\n" in file_contents:
                    # replace in current chunk
                    file_contents = file_contents.replace("\r\n", "\n")
                # check to see that the original_code is in the new_code by trying all possible indentations
                correct_indent, rstrip_original_code = manual_code_check(file_contents, original_code)
                # if the original_code couldn't be found in the chunk we need to let the llm know
                if original_code not in file_contents and correct_indent == -1:
                    if new_code.strip() and contains_ignoring_whitespace(new_code, file_contents): # TODO: this should go after checking if it's in a different file
                        error_message = "Your original_code was not found in the file but your new_code was found. This is likely because this fix has already been applied. Validate that this requested feature has already been applied. If so, call the submit_task tool."
                        break
                    # TODO: add weighted ratio to the choices, penalize whitespace less
                    best_match, best_score = find_best_match(original_code, file_contents) # TODO: this should check other files for exact to 90% match
                    if best_score > 80:
                        surrounding_lines_before, surrounding_lines_after = get_surrounding_lines(file_contents, best_match)
                        START_MARKER = "\n===== START =====\n"
                        END_MARKER = "\n===== END =====\n"

                        best_indent_score = 0
                        best_indent = 0

                        for indentation in range(0, 10):
                            indented_original_code = indent(original_code, indentation)
                            score = rapidfuzz.fuzz.ratio(indented_original_code, best_match)
                            if score > best_indent_score:
                                best_indent_score = score
                                best_indent = indentation

                        first_diff_text = surrounding_lines_before + START_MARKER + indent(original_code, best_indent) + END_MARKER + surrounding_lines_after
                        second_diff_text = surrounding_lines_before + START_MARKER + best_match + END_MARKER + surrounding_lines_after
                        best_match_diff = generate_diff(first_diff_text, second_diff_text, n=20) # this is bounded to 14 * 2 lines of context
                        error_message = f"The original_code provided does not appear to be present in file {file_name}. Your provided original_code contains:\n```\n{tool_call['original_code']}\n```\nDid you mean the following?\n```\n{best_match}\n```\nHere is the difference between the original_code and the most similar existing code from the file, along with its surrounding code:\n```\n{best_match_diff}\n```\n" + DID_YOU_MEAN_PROMPT
                    else:
                        # check other files, this code should skip if there are no other files
                        all_file_contents = list(dict.fromkeys([get_latest_contents(fcr.filename, cloned_repo, modify_files_dict) for fcr in llm_state["fcrs"] if fcr.filename != file_name]))
                        all_file_names = list(dict.fromkeys([fcr.filename for fcr in llm_state["fcrs"] if fcr.filename != file_name]))
                        best_matches = [find_best_match(original_code, file_contents) for file_contents in all_file_contents]
                        for (best_match, best_score), other_file_name in zip(best_matches, all_file_names):
                            if best_score > 80:
                                surrounding_lines_before, surrounding_lines_after = get_surrounding_lines(file_contents, best_match)
                                START_MARKER = "\n===== START =====\n"
                                END_MARKER = "\n===== END =====\n"
                                first_diff_text = surrounding_lines_before + START_MARKER + tool_call['original_code'] + END_MARKER + surrounding_lines_after
                                second_diff_text = surrounding_lines_before + START_MARKER + best_match + END_MARKER + surrounding_lines_after
                                best_match_diff = generate_diff(first_diff_text, second_diff_text, n=14) # this is bounded to 14 * 2 lines of 
                                if first_diff_text == second_diff_text or best_match_diff.strip() == "":
                                    error_message = f"The original_code provided does not appear to be present in file {file_name}. Your provided original_code contains:\n```\n{tool_call['original_code']}\n```\nThe code was found in {other_file_name}. Call make_changes again with the correct file name."
                                else:
                                    error_message = f"The original_code provided does not appear to be present in file {file_name}. Your provided original_code contains:\n```\n{tool_call['original_code']}\n```\nDid you mean the {other_file_name} file?\n```\n{best_match}\n```\nHere is the diff and surrounding code:\n```\n{best_match_diff}\n```"
                                break
                        else: # if no other file match was found then return this block
                            error_message = ORIGINAL_CODE_NOT_FOUND_PROMPT.format(
                                original_code=tool_call['original_code'],
                                file_path=file_name
                            )
                    break
                # ensure original_code and new_code has the correct indents
                new_code_lines = new_code.split("\n")
                original_code_lines = original_code.split("\n")
                if len(original_code_lines) > 1:
                    new_code = "\n".join(f'{correct_indent * " "}{line}' for line in new_code_lines)
                else:
                    new_code = f'{correct_indent * " "}{new_code.lstrip()}'
                if rstrip_original_code:
                    original_code_lines = [line.rstrip() for line in original_code.split("\n")]
                else:
                    original_code_lines = original_code.split("\n")
                if len(original_code_lines) > 1:
                    """This will match the whitespace from the code file itself"""
                    best_span = contains_ignoring_whitespace(original_code, file_contents)
                    start_line, end_line = best_span
                    original_code = "\n".join(file_contents.split("\n")[start_line:end_line])
                else:
                    original_code = f'{correct_indent * " "}{original_code.lstrip()}'
                # before we apply changes make sure original_code is unique inside current_chunk
                current_chunk_occurences = file_contents.count(original_code)
                if current_chunk_occurences > 1 and not replace_all:
                    if current_chunk_occurences * len(original_code.split("\n")) < 50:
                        # We start by setting original_code_lines with indentation fixed. Sometimes the model forgets to indent the first line.

                        # INDENTATION FIX START #
                        start_line = -1
                        min_diff = inf
                        file_contents_lines = file_contents.split("\n")
                        for index, _line in enumerate(file_contents_lines):
                            if all(original_line.lstrip() == file_contents_line.lstrip() for original_line, file_contents_line in zip(original_code_lines, file_contents_lines[index:index + len(original_code_lines)])):
                                # if abs(len(line) - len(first_line)) < min_diff:
                                current_diff = sum(abs(len(original_line) - len(file_contents_line)) for original_line, file_contents_line in zip(original_code_lines, file_contents_lines[index:index + len(original_code_lines)]))
                                if current_diff < min_diff:
                                    min_diff = current_diff
                                    start_line = index
                                    if min_diff == 0:
                                        break

                        if start_line == -1:
                            error_message = f"The original_code is not unique to the file `{file_name}`. It appears {current_chunk_occurences} times in the file. If you would like to replace all occurrences, add a `replace_all` parameter set to `true`. Otherwise, for the `original_code` to be valid, it must be unique within the file.\n\n" + MULTIPLE_OCCURRENCES_PROMPT
                            break
                            
                        original_code_lines = file_contents_lines[start_line:start_line + len(original_code_lines)]
                        # INDENTATION FIX END #

                        # Then we find all the matches and their surrounding lines.
                        matches = []
                        surrounding_lines = 10

                        for i in range(len(file_contents_lines)):
                            if "\n".join(original_code_lines) == "\n".join(file_contents_lines[i:i + len(original_code_lines)]):
                                match_ = "\n".join(file_contents_lines[max(0, i - surrounding_lines):i])
                                match_ += "\n" + "===== START =====" + "\n"
                                match_ += "\n".join(file_contents_lines[i:i + len(original_code_lines)])
                                match_ += "\n" + "===== END =====" + "\n"
                                match_ += "\n".join(file_contents_lines[i + len(original_code_lines):i + len(original_code_lines) + surrounding_lines])
                                matches.append(match_)

                        error_message = f"The original_code is not unique to the file `{file_name}`. It appears {current_chunk_occurences} times in the file. If you would like to replace all occurrences, add a `replace_all` parameter set to `true`. Otherwise, for the `original_code` to be valid, it must be unique within the file.\n\nTo resolve this issue, please provide a unique `original_code` by including some surrounding lines for context. Make sure the selected code snippet appears only once in the file. Here are the {current_chunk_occurences} occurences of the `original_code` in the file with their surrounding lines:\n\n" + "\n\n".join([f"Occurrence {i + 1}:\n```\n{match_}\n```" for i, match_ in enumerate(matches)]) + "\n" + MULTIPLE_OCCURRENCES_PROMPT
                    else:
                        error_message = f"The original_code is not unique to the file `{file_name}`. It appears {current_chunk_occurences} times in the file. If you would like to replace all occurrences, add a `replace_all` parameter set to `true`. Otherwise, for the `original_code` to be valid, it must be unique within the file.\n\n" + MULTIPLE_OCCURRENCES_PROMPT
                    break
                
                if original_code not in file_contents:
                    new_correct_indent, new_rstrip_original_code = manual_code_check(file_contents, new_code)
                    if new_correct_indent == -1:
                        error_message = f"The original_code provided does not appear to be present in file {file_name}. Your provided original_code contains:\n```\n{tool_call['original_code']}\n```\nBut this section of code was not found anywhere inside the current file."
                    else:
                        error_message = f"The original_code provided does not appear to be present in file {file_name}. However, the new_code provided is present in the file. If you would like to apply this change, please provide the correct original_code. Otherwise, call submit_task to move on to the next task."
                    break
                
                if new_code == original_code:
                    error_message += "The new_code and original_code are the same. If you are certain this change needs to be made, MAKE SURE that the new_code and original_code are NOT the same."
                    break

                # apply changes
                if replace_all:
                    new_file_contents = file_contents.replace(original_code, new_code)
                else:
                    new_file_contents = file_contents.replace(original_code, new_code, 1)
                # Check if changes were made
                if new_file_contents == file_contents:
                    logger.warning("No changes were made to the code.")
                    error_message = "No changes were made, it seems the changes you requested were not applied or made no difference to the code file."
                    break
                
                # Check if the changes are valid
                if not error_message:
                    check_results = get_check_results(file_name, new_file_contents)
                    check_results_message = check_results.is_worse_than_message(llm_state['initial_check_results'][file_name])
                    failing_parse = check_results.parse_error_message if not llm_state['initial_check_results'][file_name].parse_error_message else ""
                    current_diff = generate_diff(
                        file_contents, new_file_contents, n=10
                    )
                    if failing_parse:
                        error_message = f"Error: Invalid code changes have been applied. You requested the following changes:\n\n```diff\n{current_diff}\n```\n\nBut it produces invalid code with the following error logs:\n```\n{failing_parse}\n```\n\n" + fix_syntax_prompt
                        print(error_message)
                        breakpoint()
                        break
                    elif check_results_message:
                        warning_message = check_results_message
                        if "undefined variable" in warning_message.lower():
                            warning_message += "\n\nDouble check that the newly used variables are defined."
        if error_message:
            llm_response = f"ERROR\n\n{error_message}"
            llm_state["attempt_lazy_change"] = False
            llm_state["attempt_count"] += 1
            if llm_state["attempt_count"] > 7:
                for fcr in llm_state["fcrs"]:
                    if not fcr.is_completed:
                        fcr.is_completed = True
                        break
                llm_state['current_task'] = render_current_task(llm_state["fcrs"]) # rerender the current task
                llm_state["attempt_count"] = 0
                llm_response = f"SKIPPED\n\nThe previous task took too many attempts so we gave up. Please move on to the next task. {llm_state['current_task']}"
                if all([fcr.is_completed for fcr in llm_state["fcrs"]]):
                    llm_response = "DONE"
                llm_state["attempt_lazy_change"] = True # successful application with no warning message means we can attempt lazy change again
        if not error_message:
            success_message = (
                f"SUCCESS\n\nThe following changes have been applied to {file_name}:\n\n"
                + generate_diff(file_contents, new_file_contents, n=10)
            ) + f"{warning_message}\n\nYou can continue to make changes to the file {file_name} and call the make_change tool again, or handle the rest of the plan. REMEMBER to add all necessary imports at the top of the file, if the import is not already there!"
            diff_string = generate_diff(file_contents, new_file_contents)
            current_fcr_index = get_current_task_index(llm_state["fcrs"])
            # set contents
            if file_name not in modify_files_dict:
                modify_files_dict[file_name] = {
                    "contents": file_contents,
                    "original_contents": file_contents,
                }
            if warning_message:
                llm_response = f"SUCCESS\n\nThe following changes have been applied:\n\n```diff\n{generate_diff(file_contents, new_file_contents, n=25)}\n```\nThe code changes also yield the following warnings:\n```\n{warning_message}\n```\n\n{linter_warning_prompt.format(current_task=llm_state['current_task'])}"
                # print(llm_response)
                # breakpoint()
                modify_files_dict[file_name]['contents'] = new_file_contents
                llm_state["attempt_lazy_change"] = False # no longer attempt lazy change
                # breakpoint()
            elif llm_state["completed_changes_per_fcr"][current_fcr_index] + 1 < llm_state["changes_per_fcr"][current_fcr_index]:
                # Incomplete changes, should use a different prompt realistically
                llm_response = f"SUCCESS\n\nThe following changes have been applied:\n\n```diff\n{generate_diff(file_contents, new_file_contents, n=25)}\n```\n{self_review_prompt.format(current_task=llm_state['current_task'])}"
                modify_files_dict[file_name]['contents'] = new_file_contents
                llm_state["attempt_lazy_change"] = True

                llm_state["completed_changes_per_fcr"][current_fcr_index] += 1
            elif diff_string.count("\n+") + diff_string.count("\n-") > 10:
                llm_response = f"SUCCESS\n\nThe following changes have been applied:\n\n```diff\n{generate_diff(file_contents, new_file_contents, n=25)}\n```\n\n{self_review_prompt.format(current_task=llm_state['current_task'])}"
                # breakpoint()
                modify_files_dict[file_name]['contents'] = new_file_contents
                llm_state["attempt_lazy_change"] = False # no longer attempt lazy change
            else:
                llm_response = f"SUCCESS\n\nThe following changes have been applied:\n\n```diff\n{generate_diff(file_contents, new_file_contents, n=25)}\n```\n{self_review_prompt.format(current_task=llm_state['current_task'])}"
                modify_files_dict[file_name]['contents'] = new_file_contents

                # Success without warning, let's move onto the next task:
                changes_made = generate_diffs(modify_files_dict)
                if changes_made:
                    llm_response = "DONE"
                else:
                    llm_response = "ERROR\n\nNo changes were made. Please continue working on your task."
                for fcr in llm_state["fcrs"]:
                    if not fcr.is_completed:
                        fcr.is_completed = True
                        break
                llm_state['current_task'] = render_current_task(llm_state["fcrs"]) # rerender the current task
                llm_state["attempt_count"] = 0
                llm_response = f"SUCCESS\n\nThe previous task is now complete. Please move on to the next task. {llm_state['current_task']}"
                if all([fcr.is_completed for fcr in llm_state["fcrs"]]):
                    llm_response = "DONE"

                llm_state["attempt_lazy_change"] = True # successful application with no warning message means we can attempt lazy change again
                llm_state["completed_changes_per_fcr"][current_fcr_index] += 1
    elif tool_name == "create_file":
        error_message = ""
        success_message = ""
        for key in tool_call_parameters[tool_name]:
            if key not in tool_call:
                error_message += f"No {key} was provided in the {tool_name} tool call. Call the tool again but this time provide the {key}.\n"
        if not error_message:
            new_file_path = tool_call["file_path"].strip()
            new_file_name = tool_call["file_name"].strip()
            new_file_contents = tool_call["contents"].strip()
            new_file_dir = os.path.join(cloned_repo.repo_dir, new_file_path)
            new_full_file_path = os.path.join(new_file_path, new_file_name)
            new_full_file_path_with_cwd = os.path.join(cloned_repo.repo_dir, new_file_path, new_file_name)
            # ensure file doesn't already exist
            if os.path.exists(new_full_file_path_with_cwd):
                error_message = f"The file {new_full_file_path} already exists. Modify this existing file instead of attempting to create a new one!"
            # ensure directory is valid
            if not os.path.isdir(new_file_dir):
                error_message = f"The directory {new_file_path} is not valid. Make sure you have the correct directory path!"
            # ensure that the directory of the new full path exists, in case the file name is weird
            if not os.path.exists(os.path.dirname(new_full_file_path_with_cwd)):
                error_message = f"The directory {os.path.dirname(new_full_file_path)} does not exist. Make sure the new file you want to create exists within an existing directory!"
            # if no issues, create the file by placing it in modify_files_dict
            if not error_message:
                modify_files_dict[new_full_file_path] = {"contents": new_file_contents, "original_contents": ""}
                success_message = f"The new file {new_full_file_path} has been created successfully with the following contents:\n\n{new_file_contents}"
        if error_message:
            llm_response = f"ERROR\n\n{error_message}"
        else:
            llm_response = f"SUCCESS\n\n{success_message}"
    else:
        llm_response = f"ERROR\nUnexpected tool name: {tool_name}"
    return llm_response, modify_files_dict, llm_state

if __name__ == "__main__":
    pass