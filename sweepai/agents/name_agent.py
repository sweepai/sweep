import re
from sweepai.config.server import DEFAULT_GPT35_MODEL, DEFAULT_GPT4_32K_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message

prompt = """\
<old_code>
{old_code}
</old_code>
{snippets}
For each of the code snippets above, we want to create function names. We must not have duplicates of the existing function names as follows:
{existing_names}
Generate a function name for each of these in the below format. Use the context from the old_code and snippets to generate function names that clearly state what the function does.

<function_name>
name_of_function
</function_name>
..."""

def serialize_method_name(method_name):
    # handles '1. "method_name"' -> 'method_name'
    if "." in method_name:
        return method_name.split(". ")[-1].strip('"')
    return method_name.strip().strip('"')

class NameBot(ChatGPT):
    def name_functions(
        self,
        old_code,
        snippets,
        existing_names
    ):

        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        name_response = self.chat(
            content=prompt.format(
                    old_code=old_code,
                    snippets=snippets,
                    existing_names=existing_names
                ),
        )
        name_pattern = r"<function_name>\n(.*?)\n</function_name>"
        name_matches = list(
                re.finditer(name_pattern, name_response, re.DOTALL)
            )
        name_matches = [match.group(1) for match in name_matches]
        function_names = [serialize_method_name(
                    name_match.strip().strip('"').strip("'").strip("`")
                ) for name_match in name_matches]
        return function_names