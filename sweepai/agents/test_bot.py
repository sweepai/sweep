import re

from sweepai.agents.modify_bot import strip_backticks
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.jedi_utils import (
    get_all_defined_functions,
    get_references_from_defined_function,
    setup_jedi_for_file,
)
from sweepai.utils.regex_utils import xml_pattern
from sweepai.utils.unittest_utils import fuse_scripts

test_prompt = """\
# Code
File path: {file_path}
{changes_made}

{code}

# Instructions
Write unit tests for the above function. Cover every possible edge case using the function's dependencies."""

test_prompt_response_format = """\
<mock_identification>
# Entities to mock #
Identify all return objects from expensive operations entities we need to mock. Copy the code snippets from code_to_test that reflect where this mock is used and accessed.
```
code snippet of the mocked object's usage
```

# Access method #
Identify the access method of the entity we are trying to mock, for example, if we have `return_obj = expensive_operation()`, identify all occurrences of `return_obj.attribute` or `return_obj["key"]`.

Then, for each chain of accesses like return_obj.foo["key"].bar, list the access type at each step of the chain and how they should be mocked, like
- return_obj.foo is an attribute method so return_obj should be mocked like MagicMock.foo
- return_obj.foo["key"] is a dictionary access so return_obj.foo should be mocked like {{"key": MagicMock}}
- return_obj.foo["key"].bar is an attribute method so return_obj.foo["key"] should be mocked like MagicMock.bar

# Mock Code #
Write a mock that perfectly mocks this access method.
</mock_identification>

<code>
Unit test that uses the mocked response and expected behavior.
</code>"""

test_system_prompt = f"""\
You're an expert Python QA engineer and your job is to write a unit test for the following. Respond in the following format:

{test_prompt_response_format}"""

test_user_prompt = rf"""<code_to_test>
{{code_to_test}}
</code_to_test>

Write a unit test for the OpenAIProxy.call_openai method. Respond in the following format:

{test_prompt_response_format}"""


# This class should handle appending or creating new tests
class TestBot(ChatGPT):
    def write_test(
        self,
        additional_messages: list[Message] = [],
        snippets_str="",
        file_path: str = "",
        update_snippets_code: str = "",
        request="",
        changes_made="",
        cloned_repo: ClonedRepo = None,
        **kwargs,
    ):
        # self.model = (
        #     DEFAULT_GPT4_32K_MODEL
        #     if (self.chat_logger and self.chat_logger.is_paying_user())
        #     else DEFAULT_GPT35_MODEL
        # )
        self.messages = [
            Message(
                role="system",
                content=test_system_prompt,
                key="system",
            )
        ]
        self.messages.extend(additional_messages)

        script, tree = setup_jedi_for_file(
            project_dir=cloned_repo.cache_dir,
            file_full_path=f"{cloned_repo.cache_dir}/{file_path}",
        )

        all_defined_functions = get_all_defined_functions(script=script, tree=tree)
        generated_code_sections = []
        for fn_def in all_defined_functions:
            full_file_code = cloned_repo.get_file_contents(file_path)
            script, tree = setup_jedi_for_file(
                project_dir=cloned_repo.cache_dir,
                file_full_path=f"{cloned_repo.cache_dir}/{file_path}",
            )
            function_and_reference = get_references_from_defined_function(
                fn_def,
                script,
                tree,
                f"{cloned_repo.cache_dir}/{file_path}",
                full_file_code,
            )
            if function_and_reference.function_code.count("\n") < 20:
                continue
            recent_file_contents = cloned_repo.get_file_contents(file_path=file_path)
            code = f"<original_code>\n{recent_file_contents}</original_code>\n"
            code += function_and_reference.serialize(tag="function_to_test")
            extract_response = self.chat(
                test_user_prompt.format(
                    code_to_test=function_and_reference.function_code
                )
            )
            self.messages = self.messages[:-2]

            generated_code = re.search(xml_pattern("code"), extract_response, re.DOTALL)
            generated_code = strip_backticks(generated_code.group(1))
            generated_code_sections.append(generated_code)
        return fuse_scripts(generated_code_sections)
