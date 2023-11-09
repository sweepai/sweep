from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message

from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.jedi_utils import (
    get_all_defined_functions,
    get_references_from_defined_function,
    setup_jedi_for_file,
)

test_prompt = """\
# Code
File path: {file_path}
{changes_made}

{code}

# Instructions
Write unit tests for the above function. Cover every possible edge case using the function's dependencies."""

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
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        self.messages = [
            Message(
                role="system",
                content="",
                key="system",
            )
        ]
        self.messages.extend(additional_messages)

        script, tree = setup_jedi_for_file(
            project_dir=cloned_repo.cache_dir,
            file_full_path=f"{cloned_repo.cache_dir}/{file_path}",
        )

        all_defined_functions = get_all_defined_functions(script=script, tree=tree)
        new_code = None
        change_sets = []
        extracted_exact_matches = []
        new_function_names = []
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
            # everything below must operate in a loop
            recent_file_contents = cloned_repo.get_file_contents(file_path=file_path)
            code = f"<original_code>\n{recent_file_contents}</original_code>\n"
            code += function_and_reference.serialize(tag="function_to_test")
            import pdb; pdb.set_trace()
            # extract_response = self.chat(
            #     test_prompt.format(
            #         code=code,
            #         file_path=file_path,
            #         snippets=snippets_str,
            #         changes_made=changes_made,
            #     )
            # )
            self.messages = self.messages[:-2]
        return new_code
