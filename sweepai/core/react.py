"""
Utils for react agent
"""

import re
from textwrap import dedent
from typing import Callable

from pydantic import BaseModel

REACT_INITIAL_PROMPT = """
Gather information to solve the above problem using the tools below. 
* You should use the tools about 2-3 times
* Only use Finish when you are CERTAIN you have enough information to solve the problem. More information is usually better.
* The examples are provided ONLY as examples: the example inputs probably will not work
* You are given the following tools:

{tools}

Respond in the following format, first thinking logically and deriving a plan, then respond with the tool, and inputs replaced by their values:
Thoughts:
1. thought_1
2. thought_2
...
Plan: 
1. plan_1
2. plan_2
...
<tool>tool</tool>
<inputs>
inputs
</inputs>
"""

REACT_RESPONSE_PROMPT = """
The tool returned the following output.

<output>
{output}
</output>

What would you like to do next? Use the same format as above.
"""


def dedent(text: str) -> str:
    return re.sub(r'(\n)[ \t]+', r'\n', text.strip())


class Tool(BaseModel):
    description: str
    function: Callable[[str], str]
    example_inputs: str = ""
    name: str = ""

    @property
    def _name(self):
        return self.__class__.__name__ if self.name == "" else self.name

    @property
    def summary(self):
        return dedent(f"""
        {self._name}: {self.description}
        Example usage:
        <tool>{self._name}</tool>
        <inputs>
        {self.example_inputs}
        </inputs>
        """.strip())

    def __call__(self, *args, **kwargs):
        return self.function(*args, **kwargs)

    @classmethod
    def tool(cls, **kwargs):
        def decorator(function):
            return cls(function=function, **kwargs)

        return decorator


class CodeSearch(Tool):
    description = "Search in the codebase for relevant snippets of code. Takes natural language search query as input."
    example_inputs = "Modal component on main page."


class ReadFiles(Tool):
    description = "Reads listed files. Takes list of literal file paths as input, separated by newlines. Max 3 files."
    example_inputs = "src/main.py\ntests/test_main.py\ntests/test_utils.py:101:200"


class Google(Tool):
    description = "Search for code documentation on Google. Takes natural language search query as input."
    example_inputs = "Discord API docs"


class Finish(Tool):
    description = "Indicate you have sufficient information to move forward with making changes to the codebase. Return with an empty string."
    example_inputs = ""
    function = lambda _: ""


class Toolbox(BaseModel):
    tools: list[Tool] = []

    @property
    def prompt(self):
        return REACT_INITIAL_PROMPT.format(tools="\n\n".join([tool.summary for tool in self.tools]))

    class ParsedResults(BaseModel):
        tool_name: str
        inputs: str
        _regex: str = r"<tool>(?P<tool>.*?)</tool>\s+<inputs>(?P<inputs>.*?)</inputs>"

        @classmethod
        def parse(cls, results) -> "Toolbox.ParsedResults":
            match = re.search(cls._regex, results, flags=re.DOTALL)
            return cls(tool_name=match.group("tool").strip(), inputs=match.group("inputs").strip())

    def process_results(self, parsed_results: "Toolbox.ParsedResults") -> str:
        # parsed_results = Toolbox.ParsedResults.parse(raw_output)
        tool = next((tool for tool in self.tools if tool._name == parsed_results.tool_name), None)
        return tool(parsed_results.inputs)
