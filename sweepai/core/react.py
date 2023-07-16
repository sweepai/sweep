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


# The Tool class represents a tool that can be used by the AI. It has a description, a function that it performs, example inputs, and a name.
class Tool(BaseModel):
    description: str
    function: Callable[[str], str]
    example_inputs: str = ""
    name: str = ""

    # The _name property returns the name of the class if no name is provided.
    @property
    def _name(self):
        return self.__class__.__name__ if self.name == "" else self.name

    # The summary property returns a summary of the tool, including its name, description, and example usage.
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

    # The __call__ method allows the tool to be called as a function.
    def __call__(self, *args, **kwargs):
        return self.function(*args, **kwargs)

    # The tool method is a class method that returns a decorator which can be used to create a new tool.
    @classmethod
    def tool(cls, **kwargs):
        def decorator(function):
            return cls(function=function, **kwargs)

        return decorator

# The CodeSearch class represents a tool that searches the codebase for relevant snippets of code.
class CodeSearch(Tool):
    description = "Search in the codebase for relevant snippets of code. Takes natural language search query as input."
    example_inputs = "Modal component on main page."

# The ReadFiles class represents a tool that reads listed files.
class ReadFiles(Tool):
    description = "Reads listed files. Takes list of literal file paths as input, separated by newlines. Max 3 files."
    example_inputs = "src/main.py\ntests/test_main.py\ntests/test_utils.py:101:200"

# The Google class represents a tool that searches for code documentation on Google.
class Google(Tool):
    description = "Search for code documentation on Google. Takes natural language search query as input."
    example_inputs = "Discord API docs"

# The Finish class represents a tool that indicates the user has sufficient information to move forward with making changes to the codebase.
class Finish(Tool):
    description = "Indicate you have sufficient information to move forward with making changes to the codebase. Return with an empty string."
    example_inputs = ""
    function = lambda _: ""

# The Toolbox class represents a collection of tools.
class Toolbox(BaseModel):
    tools: list[Tool] = []

    # The prompt property returns the initial prompt for the AI, formatted with the summaries of all the tools.
    @property
    def prompt(self):
        return REACT_INITIAL_PROMPT.format(tools="\n\n".join([tool.summary for tool in self.tools]))

    # The ParsedResults class represents the results of parsing the raw output of a tool.
    class ParsedResults(BaseModel):
        tool_name: str
        inputs: str
        _regex: str = r"<tool>(?P<tool>.*?)</tool>\s+<inputs>(?P<inputs>.*?)</inputs>"

        # The parse method parses the raw output and returns a ParsedResults object.
        @classmethod
        def parse(cls, results) -> "Toolbox.ParsedResults":
            match = re.search(cls._regex, results, flags=re.DOTALL)
            return cls(tool_name=match.group("tool").strip(), inputs=match.group("inputs").strip())

    # The process_results method processes the parsed results and returns the output of the corresponding tool.
    def process_results(self, parsed_results: "Toolbox.ParsedResults") -> str:
        tool = next((tool for tool in self.tools if tool._name == parsed_results.tool_name), None)
        return tool(parsed_results.inputs)
