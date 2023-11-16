import re
from typing import Callable

from sweepai.agents.modify_bot import strip_backticks
from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, SandboxResponse
from sweepai.utils.autoimport import add_auto_imports
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.jedi_utils import (
    get_all_defined_functions,
    get_references_from_defined_function,
    setup_jedi_for_file,
)
from sweepai.utils.regex_utils import xml_pattern
from sweepai.utils.unittest_utils import fuse_scripts, split_script

test_prompt = """\
# Code
File path: {file_path}
{changes_made}

{code}

# Instructions
Write unit tests for the above function. Cover every possible edge case using the function's dependencies."""

test_prompt_response_format = """\
<mock_identification>
# Entities to mock
Identify all return objects from expensive operations entities we need to mock. Copy the code snippets from code_to_test that reflect where this mock is used and accessed.
```
code snippet of each mocked object's usage
```

# Access method
Identify the access method of each entity we are trying to mock, for example, if we have `return_obj = expensive_operation()`, identify all occurrences of `return_obj.attribute` or `return_obj["key"]`.

Then, for each chain of accesses like return_obj.foo["key"].bar, list the access type at each step of the chain and how they should be mocked, like
- return_obj.foo is an attribute method so return_obj should be mocked like MagicMock.foo
- return_obj.foo["key"] is a dictionary access so return_obj.foo should be mocked like {{"key": MagicMock}}
- return_obj.foo["key"].bar is an attribute method so return_obj.foo["key"] should be mocked like MagicMock.bar

# Mock Code
Write mocks that perfectly mock these access methods. E.g.
```
from unittest.mock import MagicMock

mock_response = MagicMock()
mock_response.foo = {{}}
mock_response.foo["key"] = MagicMock()
mock_response.foo["key"].bar = "mock content"
```
</mock_identification>

<code>
Unit test that uses the mocked response in the setUp method (and optionally the tearDown method).
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

test_extension_planning_user_prompt = f"""
<code_to_test>
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
List any constants and functions that NEED to be modified for the unit test to work as expected, apart from the existing setUp and tearDown functions, and whether they should be patched like patch("module.CONSTANT", NEW_CONSTANT) or patch("module.function").
</planning>

<additional_unit_tests>
```
The additional unit test that uses the mocks defined in the original unit test. Format it like

class TestNameOfFullFunctionName(unittest.TestCase):
    ...

    def test_function(self, mocks...):
        ... # the test here
```
</additional_unit_tests>"""

test_extension_system_prompt = rf"""You're an expert Python QA engineer and your job is to write a unit test for the following. Respond in the following format:

{test_extension_format}"""

test_extension_user_prompt = rf"""<code_to_test>
{{code_to_test}}
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


def skip_last_test(
    test_code: str, message: str = "Skipping due to failing test"
) -> str:
    """Skip the last test in a test file, placing @unittest.skip before other decorators."""
    code_before, last_test = test_code.rsplit("    def test_", 1)

    decorator_pattern = r"(\s+@[\w\.]+\([^\)]*\)\s+)*"
    match = re.search(decorator_pattern + r"def test_" + last_test, test_code)

    skipped_test = f'    @unittest.skip("{message}")\n'

    if match:
        decorators = match.group(1) if match.group(1) is not None else ""
        skipped_test += decorators

    skipped_test += f"    def test_" + last_test

    return code_before + skipped_test


def pascal_case(s: str) -> str:
    """Convert a string to PascalCase."""
    return "".join(word.capitalize() for word in s.split("_"))


# This class should handle appending or creating new tests
class TestBot(ChatGPT):
    def write_test(
        self,
        additional_messages: list[Message] = [],
        snippets_str="",
        file_path: str = "",  # file path of the source file to test
        update_snippets_code: str = "",
        request="",
        changes_made="",
        cloned_repo: ClonedRepo = None,
        changed_files: list[tuple[str, str]] = [],
        check_sandbox: Callable[
            [str, str, str], tuple[str, SandboxResponse]
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
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        self.messages = [
            Message(
                role="system",
                content=test_system_prompt,
                key="system",
            )
        ]
        self.messages.extend(additional_messages)

        test_extension_planner = ChatGPT.from_system_message_string(
            test_extension_planning_system_prompt, chat_logger=self.chat_logger
        )
        test_extension_planner.messages.extend(additional_messages)

        test_extension_creator = ChatGPT.from_system_message_string(
            test_extension_system_prompt, chat_logger=self.chat_logger
        )
        test_extension_creator.messages.extend(additional_messages)

        script, tree = setup_jedi_for_file(
            project_dir=cloned_repo.repo_dir,
            file_full_path=f"{cloned_repo.repo_dir}/{file_path}",
        )

        all_defined_functions = get_all_defined_functions(script=script, tree=tree)
        generated_code_sections = []
        for fn_def in all_defined_functions:
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
            if function_and_reference.function_code.count("\n") < 20:
                continue
            recent_file_contents = cloned_repo.get_file_contents(file_path=file_path)
            code = f"<original_code>\n{recent_file_contents}</original_code>\n"
            code += function_and_reference.serialize(tag="function_to_test")
            extract_response = self.chat(
                test_user_prompt.format(
                    code_to_test=function_and_reference.function_code,
                    method_name=function_and_reference.function_name,
                )
            )
            self.messages = self.messages[:-2]

            code_xml_pattern = xml_pattern("code")

            generated_test = re.search(code_xml_pattern, extract_response, re.DOTALL)
            generated_test = strip_backticks(str(generated_test.group("code")))

            current_unit_test = generated_test

            current_unit_test = current_unit_test.replace(
                "(unittest.TestCase)",
                pascal_case(fn_def.name.split(".")[-1]) + "(unittest.TestCase)",
                1,
            )

            # Check the unit test here and try to fix it
            extension_plan_results = test_extension_planner.chat(
                test_extension_planning_user_prompt.format(
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

            _, sandbox_response = check_sandbox(
                file_path,
                current_unit_test,
                changed_files,
            )
            if sandbox_response.success == False:
                skip_last_test(current_unit_test)

            for test_cases_batch in additional_test_cases[
                : min(1, len(additional_test_cases))
            ]:
                extension_test_results = test_extension_creator.chat(
                    test_extension_user_prompt.format(
                        code_to_test=function_and_reference.function_code,
                        current_unit_test=current_unit_test,
                        method_name=function_and_reference.function_name,
                        test_cases=test_cases_batch.strip(),
                    )
                )
                extension_test_results = re.search(
                    xml_pattern("additional_unit_tests"),
                    extension_test_results,
                    re.DOTALL,
                )
                extension_test_results = strip_backticks(
                    str(extension_test_results.group("additional_unit_tests"))
                )

                definitions = split_script(extension_test_results).definitions
                definitions = definitions.split("\n\n", maxsplit=1)[1:]

                decomposed_script = split_script(current_unit_test)
                current_unit_test = "\n\n".join(
                    [
                        decomposed_script.imports,
                        decomposed_script.definitions,
                        "\n\n".join(definitions),
                        decomposed_script.main,
                    ]
                )

                _, sandbox_response = check_sandbox(
                    file_path,
                    current_unit_test,
                    changed_files,
                )
                if sandbox_response.success == False:
                    skip_last_test(current_unit_test)

            generated_code_sections.append(current_unit_test)

        final_code = fuse_scripts(generated_code_sections, do_remove_main=False)
        final_code = add_auto_imports(file_path, cloned_repo.repo_dir, final_code)
        return final_code
