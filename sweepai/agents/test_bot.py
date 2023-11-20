from __future__ import nested_scopes

import json
import re
from pathlib import Path
from typing import Any, Callable

from sweepai.agents.modify_bot import strip_backticks
from sweepai.config.server import DEBUG, DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, Message, SandboxResponse
from sweepai.utils.autoimport import add_auto_imports
from sweepai.utils.coverage_renderer import render_coverage_data
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.jedi_utils import (
    get_all_defined_functions,
    get_function_references,
    get_parent_class_reference,
    get_references_from_defined_function,
    setup_jedi_for_file,
    summarize_code,
)
from sweepai.utils.regex_utils import xml_pattern
from sweepai.utils.unittest_utils import (
    fuse_scripts,
    remove_constants_from_imports,
    split_script,
)

test_prompt = """\
# Code
File path: {file_path}
{changes_made}

{code}

# Instructions
Write unit tests for the above function. Cover every possible edge case using the function's dependencies."""

test_prompt_response_format = """\
<planning_and_mocks_identification>
# Entities to mock
Identify all return objects from expensive operations entities we need to mock. Copy the code snippets from code_to_test that reflect where this mock is used and accessed.
```
code snippet of each mocked object's usage
```
Then, for each item to be mocked, identify the source of them. ie. first_expensive_operation is from current_module so the patch will be current_module.first_expensive_operation whereas second_expensive_operation is from imported_module so the patch will be imported_module.second_expensive_operation.

# Access pattern
Identify the access method of each entity we are trying to mock, for example, if we have `return_obj = expensive_operation()`, identify all occurrences of `return_obj.attribute` or `return_obj["key"]`. Then, write mocks that perfectly mock these access methods. E.g.
```
from unittest.mock import MagicMock

mock_expensive_operation = MagicMock()
mock_expensive_operation.return_value.foo["key"].bar = "mock content"
```

# Patch Code
Use the `patch` decorator to mock the methods. Do not use keyword arguments in the `patch` decorator. Instead, set the return value of the mock inside the test function using the `.return_value` attribute of the mock object. Use the standard mocking behavior provided by `unittest.mock`. E.g.
```
from unittest.mock import patch

@patch("current_module.CONSTANT", "new constant")
@patch("current_module.first_expensive_operation")
@patch("imported_module.second_expensive_operation")
def test_code_to_test(self, mock_second_expensive_operation, mock_first_expensive_operation):
    mock_first_expensive_operation.return_value = first_mock_response
    mock_second_expensive_operation.return_value = second_mock_response
```
Warning: when stacking @patch decorators in Python tests, the injected mocks enter the test method in reverse order. The first decorator's mock ends up as the last argument, and vice versa. Also, you don't need to add patched constants into the arguments.
</planning_and_mocks_identification>

<code>
```
Unit test that uses the mocked response in the setUp method (and optionally the tearDown method). Use the `patch` decorator to mock the methods. Do not use keyword arguments like `new` or `new_callable` in the `patch` decorator. Instead, set the return value of the mock inside the test function using the `.return_value` attribute of the mock object.
```
</code>"""

test_system_prompt = f"""\
You're an expert Python QA engineer and your job is to write a unit test for the following. Respond in the following format:

{test_prompt_response_format}"""

test_user_prompt = rf"""<code_to_test>
{{code_to_test}}
</code_to_test>

Write a unit test using the unittest module for the {{method_name}} method. Respond in the following format:

{test_prompt_response_format}"""

test_extension_planning_format = """\
<additional_test_cases>
<test_case>
Cases to unit test in natural language. Batch similar test cases with different parameters into a singular test case. Be complete and thorough but concise. Consolidate redundant statements.
</test_case>
<test_case>
More cases to unit test.
</test_case>
...
</additional_test_cases>"""

test_extension_planning_system_prompt = f"""You're an expert Python QA engineer and your job is to write a unit test for the following. Respond in the following format:

{test_extension_planning_format}"""

test_extension_planning_user_prompt = f"""<code_to_test>
{{code_to_test}}
</code_to_test>

<current_unit_test>
```
{{current_unit_test}}
```
</current_unit_test>

Extend the unit tests using the unittest module for the {{method_name}} method. Respond in the following format:

{test_extension_planning_format}"""

test_extension_format = """\
<planning>
List any constants and functions that NEED to be modified for the unit test to work as expected, apart from the existing setUp and tearDown functions. Then for each entity, use the `patch` decorator to mock the methods. Do not use keyword arguments in the `patch` decorator. Instead, set the return value of the mock inside the test function using the `.return_value` attribute of the mock object. Use the standard mocking behavior provided by `unittest.mock`.
</planning>

<additional_unit_tests>
The additional unit test uses the mocks defined in the original unit test. Format it like

```
import unittest
from unittest.mock import patch
# any other imports

class TestNameOfFullFunctionName(unittest.TestCase):
    # copy the setUp code

    # patches
    def test_function(self, mocks...):
        ... # the test here
```

Only use patch in one of these two ways.
</additional_unit_tests>"""

test_extension_format = """\
<planning>
List any constants and functions that NEED to be modified for the unit test to work as expected. Then for each entity, use the `patch` or `patch.object` decorator to mock the methods. Do not use keyword arguments in the decorator. Instead, set the return value of the mock inside the test function using the `.return_value` attribute of the mock object. Use the standard mocking behavior provided by `unittest.mock`.
</planning>

<additional_unit_tests>
The additional unit test uses the mocks defined in the original unit test. Format it like

```
import unittest
from unittest.mock import patch

class TestNameOfFullFunctionName(unittest.TestCase):
    ...

    @patch("module.CONSTANT", "new constant")
    @patch("module.function")
    def test_function(self, mock_function):
        mock_function.return_value = "forced value"
        ... # the test here
```

Only use patch in one of these two ways.
</additional_unit_tests>"""

test_extension_system_prompt = rf"""You're an expert Python QA engineer and your job is to write a unit test for the following. Respond in the following format:

{test_extension_format}"""

test_extension_user_prompt = rf"""<code_to_test>
```
{{code_to_test}}
```
</code_to_test>

<current_unit_test>
```
{{current_unit_test}}
```
</current_unit_test>

Test cases:
{{test_cases}}

Extend the unit tests using the unittest module for the {{method_name}} method to cover the test cases. Respond in the following format:

{test_extension_format}"""


fix_unit_test_prompt = """\
{error_message}

Think step by step in planning and write the new unit test in additional_unit_tests, all in the following format:

<planning>
What went wrong? What changes should be made to the unit test? Be specific and concise.
</planning>

<additional_unit_tests>
```
# imports

class TestNameOfFullFunctionName(unittest.TestCase):
    # copy the setUp code

    # patches
    def test_function(self):
        ... # the test here
```
</additional_unit_tests>
"""

additional_unit_tests_xml_pattern = r"<additional_unit_tests>(.*?)```(python)?(?P<additional_unit_tests>.*?)(```\n)?</additional_unit_tests>"


def skip_last_test(
    test_code: str, message: str = "Skipping due to failing test"
) -> str:  # this is broken, will fix tomorrow
    """Skip the last test in a test file, placing @unittest.skip before other decorators."""
    decomposed_code = split_script(test_code)
    *code_before, last_test = re.split(
        "(?=\n\s+@patch|def )", decomposed_code.definitions
    )
    serialized_message = message.replace('"', '\\"')
    skipped_test = f'    @unittest.skip("{serialized_message}")\n    ' + last_test
    new_code = "\n\n".join([*code_before, skipped_test])

    return "\n\n".join(
        [
            decomposed_code.imports,
            new_code,
            decomposed_code.main,
        ]
    )


def pascal_case(s: str) -> str:
    """Convert a string to PascalCase."""
    return "".join(word.capitalize() for word in s.split("_"))


def determine_pip_or_poetry(repo_base: str):
    """Determine whether a repo uses pip or poetry."""
    if (Path(repo_base) / "pyproject.toml").exists():
        return "poetry"
    return "pip"


# This class should handle appending or creating new tests
class TestBot(ChatGPT):
    def write_test(
        self,
        file_change_request: FileChangeRequest,
        additional_messages: list[Message] = [],
        file_path: str = "",  # file path of the source file to test
        update_snippets_code: str = "",
        request="",
        changes_made="",
        cloned_repo: ClonedRepo = None,
        changed_files: list[tuple[str, str]] = [],
        check_sandbox: Callable[
            [str, str, str, str], tuple[str, SandboxResponse]
        ] = lambda *args: SandboxResponse(
            success=True,
            error_messages=[],
            output="",
            executions=[],
            updated_content="",
            sandbox_dict={},
        ),
        **kwargs,
    ):
        test_file_path = file_path.replace(".py", "_test.py")
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        if DEBUG:
            self.model = DEFAULT_GPT4_32K_MODEL
        self.messages = [
            Message(
                role="system",
                content=test_system_prompt,
                key="system",
            )
        ]
        self.messages.extend(additional_messages)

        test_extension_planner: ChatGPT = ChatGPT.from_system_message_string(
            test_extension_planning_system_prompt, chat_logger=self.chat_logger
        )
        test_extension_planner.messages.extend(additional_messages)

        test_extension_creator: ChatGPT = ChatGPT.from_system_message_string(
            test_extension_system_prompt, chat_logger=self.chat_logger
        )
        test_extension_creator.messages.extend(additional_messages)

        script, tree = setup_jedi_for_file(
            project_dir=cloned_repo.repo_dir,
            file_full_path=f"{cloned_repo.repo_dir}/{file_path}",
        )

        file_contents = cloned_repo.get_file_contents(file_path)
        decomposed_script = split_script(file_contents)
        remove_constants_from_imports(decomposed_script.imports)

        all_defined_functions = get_all_defined_functions(script=script, tree=tree)
        generated_code_sections = []
        for fn_def in all_defined_functions[:3]:
            if "__init__" in fn_def.name:
                continue
            full_file_code = cloned_repo.get_file_contents(file_path)
            script, tree = setup_jedi_for_file(
                project_dir=cloned_repo.repo_dir,
                file_full_path=f"{cloned_repo.repo_dir}/{file_path}",
            )
            function_and_reference = get_references_from_defined_function(
                fn_def,
                script,
                tree,
                f"{cloned_repo.repo_dir}/{file_path}",
                full_file_code,
            )
            parent_scope = fn_def.parent()  # this is the class of the method
            summarized_parent_class = ""
            if parent_scope.type == "class":
                parent_class_reference = get_parent_class_reference(
                    parent_scope, script
                )
                if parent_class_reference is not None:
                    function_and_reference.function_code = (
                        f"class {parent_scope.name}({parent_class_reference.name}):\n    ...\n\n"
                        + function_and_reference.function_code
                    )
                    parent_class_definition = script.goto(
                        parent_class_reference.line, parent_class_reference.column
                    )[0]
                    parent_class_file_contents = open(
                        parent_class_definition.module_path
                    ).read()
                    start, end, parent_class_code = get_function_references(
                        parent_class_definition, ""
                    )
                    parent_imports = remove_constants_from_imports(
                        split_script(parent_class_file_contents).imports
                    )
                    summarized_parent_class = f'<parent_class entity="{parent_class_definition.module_name}:{start}-{end}">\n{parent_imports}\n\n...\n\n{summarize_code(parent_class_code)}\n</parent_class>\n\n'
                else:
                    function_and_reference.function_code = (
                        f"class {parent_scope.name}:\n    ...\n\n"
                        + function_and_reference.function_code
                    )
            imports = remove_constants_from_imports(split_script(file_contents).imports)
            function_and_reference.function_code = (
                imports + "\n\n" + function_and_reference.function_code
            )
            if function_and_reference.function_code.count("\n") < 15:
                continue
            recent_file_contents = cloned_repo.get_file_contents(file_path=file_path)
            code = f"<original_code>\n{recent_file_contents}</original_code>\n"
            code += function_and_reference.serialize(tag="function_to_test")
            self.delete_messages_from_chat("test_user_prompt")
            self.delete_messages_from_chat("fix_unit_test_prompt")
            extract_response = self.chat(
                summarized_parent_class
                + test_user_prompt.format(
                    code_to_test=function_and_reference.function_code,
                    method_name=function_and_reference.function_name,
                ),
                message_key="test_user_prompt",
            )

            code_xml_pattern = r"<code>(.*?)```(python)?(?P<code>.*?)(```\n)?</code>"

            generated_test = re.search(code_xml_pattern, extract_response, re.DOTALL)
            generated_test = strip_backticks(str(generated_test.group("code")))

            generated_test = generated_test.replace(
                "(unittest.TestCase)",
                pascal_case(fn_def.name.split(".")[-1]) + "(unittest.TestCase)",
                1,
            )

            current_unit_test = generated_test
            _, sandbox_response = check_sandbox(
                test_file_path,
                current_unit_test,
                changed_files,
            )

            if sandbox_response.error_messages and sandbox_response.success == False:
                new_extension_tests = self.chat(
                    fix_unit_test_prompt.format(
                        error_message=sandbox_response.error_messages[-1]
                    ),
                    message_key="fix_unit_test_prompt",
                )
                new_extension_tests = re.search(
                    additional_unit_tests_xml_pattern,  # xml_pattern("additional_unit_tests"),
                    new_extension_tests,
                    re.DOTALL,
                )
                current_unit_test = strip_backticks(
                    str(new_extension_tests.group("additional_unit_tests"))
                )
                _, sandbox_response = check_sandbox(
                    test_file_path,
                    current_unit_test,
                    changed_files,
                )
                if (
                    sandbox_response.error_messages
                    and sandbox_response.success == False
                ):
                    reason = sandbox_response.error_messages[-1].splitlines()[-1]
                    current_unit_test = skip_last_test(current_unit_test, reason)

            # Check the unit test here and try to fix it
            extension_plan_results = test_extension_planner.chat(
                summarized_parent_class
                + test_extension_planning_user_prompt.format(
                    code_to_test=function_and_reference.function_code,
                    current_unit_test=current_unit_test,
                    method_name=function_and_reference.function_name,
                )
            )

            additional_test_cases = [
                match_.group("test_case")
                for match_ in re.finditer(
                    xml_pattern("test_case"), extension_plan_results, re.DOTALL
                )
            ]

            for test_cases_batch in additional_test_cases[
                : min(1, len(additional_test_cases))
            ]:
                test_extension_creator.delete_messages_from_chat(
                    "test_extension_user_prompt"
                )
                test_extension_creator.delete_messages_from_chat("fix_unit_test_prompt")
                extension_test_results = test_extension_creator.chat(
                    summarized_parent_class
                    + test_extension_user_prompt.format(
                        code_to_test=function_and_reference.function_code,
                        current_unit_test=generated_test,
                        method_name=function_and_reference.function_name,
                        test_cases=test_cases_batch.strip(),
                    ),
                    message_key="test_extension_user_prompt",
                )
                extension_test_results = re.search(
                    additional_unit_tests_xml_pattern,
                    extension_test_results,
                    re.DOTALL,
                )
                extension_test_results = strip_backticks(
                    str(extension_test_results.group("additional_unit_tests"))
                )

                _, sandbox_response = check_sandbox(
                    test_file_path,
                    extension_test_results,
                    changed_files,
                )

                if (
                    sandbox_response.error_messages
                    and sandbox_response.success == False
                ):
                    new_extension_tests = test_extension_creator.chat(
                        fix_unit_test_prompt.format(
                            error_message=sandbox_response.error_messages[-1]
                        ),
                        message_key="fix_unit_test_prompt",
                    )
                    new_extension_tests = re.search(
                        additional_unit_tests_xml_pattern,  # xml_pattern("additional_unit_tests"),
                        new_extension_tests,
                        re.DOTALL,
                    )
                    new_extension_tests = strip_backticks(
                        str(new_extension_tests.group("additional_unit_tests"))
                    )
                    _, sandbox_response = check_sandbox(
                        test_file_path,
                        new_extension_tests,
                        changed_files,
                    )
                    if (
                        sandbox_response.error_messages
                        and sandbox_response.success == False
                    ):
                        reason = sandbox_response.error_messages[-1].splitlines()[-1]
                        new_extension_tests = skip_last_test(
                            new_extension_tests, reason
                        )

                decomposed_extension_script = split_script(extension_test_results)
                _prefix, *tests = re.split(
                    "(?=\n\s+@patch|def test)",
                    decomposed_extension_script.definitions,
                )
                new_tests = "".join(tests)

                decomposed_script = split_script(current_unit_test)
                current_unit_test = "\n\n".join(
                    [
                        decomposed_script.imports,
                        decomposed_extension_script.imports,
                        decomposed_script.definitions,
                        new_tests,
                        decomposed_script.main,
                    ]
                )

            generated_code_sections.append(current_unit_test)

        final_code = fuse_scripts(generated_code_sections, do_remove_main=False)
        final_code = add_auto_imports(file_path, cloned_repo.repo_dir, final_code)

        _, sandbox_response = check_sandbox(
            test_file_path,
            final_code,
            changed_files,
            [
                "poetry add coverage",
                f"PYTHONPATH=. poetry run coverage run {test_file_path}",
                f"PYTHONPATH=. poetry run coverage json --include={file_path}",
                "cat coverage.json",
            ]
            if determine_pip_or_poetry(cloned_repo.repo_dir) == "poetry"
            else [
                "pip install coverage",
                f"PYTHONPATH=. coverage run {test_file_path}",
                f"PYTHONPATH=. coverage json --include={file_path}",
                "cat coverage.json",
            ],
        )
        if sandbox_response.success == True:
            coverage_results = json.loads(sandbox_response.outputs[-1])
            table = render_coverage_data(coverage_results, cloned_repo.repo_dir)
            file_change_request.instructions += "\n\n" + table
        else:
            file_change_request.instructions += f"\n\nTest coverage generation failed with error:\n\n```{sandbox_response.error_messages[-1]}```"
        return final_code

    def auto_fix_test(
        self, bot: ChatGPT, sandbox_response: SandboxResponse, check_sandbox: Any
    ):
        new_tests = bot.chat(
            fix_unit_test_prompt.format(
                error_message=sandbox_response.error_messages[-1]
            ),
            message_key="fix_unit_test_prompt",
        )
        new_tests = re.search(
            additional_unit_tests_xml_pattern,
            new_tests,
            re.DOTALL,
        )
        new_tests = strip_backticks(str(new_tests.group("additional_unit_tests")))
        return new_tests
