# ensure that all additional_messages are 32768 characters at most, if not split them
from dataclasses import dataclass
import re
import textwrap
from typing import Callable
from sweepai.core.chat import ChatGPT, parse_function_call_parameters
from sweepai.core.entities import Message
from typing import get_type_hints

from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall

MAX_CHARS = 32000

@dataclass
class Parameter:
    description: str

@dataclass
class Tool:
    name: str
    parameters: list[str]
    parameters_explanation: dict[str, str]
    function: Callable
    description: str = ""

    def get_xml(
        self,
        include_function_call_tags: bool = True,
        include_description: bool = True
    ):
        parameters_xml = "\n".join(f"<{parameter}>\n{self.parameters_explanation[parameter]}\n</{parameter}>" for parameter in self.parameters)
        function_xml = f"""<{self.name}>
{parameters_xml}
</{self.name}>"""
        if include_function_call_tags:
            function_xml += f"<function_call>\n{function_xml}\n</function_call>"
        if include_description and self.description:
            function_xml = f"{self.name} - {self.description}\n\n{function_xml}"
        return function_xml
    
    def __call__(self, *args, **kwargs):
        return self.function(*args, **kwargs)

def tool(**kwargs):
    def decorator(func):
        type_hints = get_type_hints(func)
        func_params = func.__code__.co_varnames[: func.__code__.co_argcount]
        parameters_explanation = {}
        parameters = []
        for parameter in func_params:
            if isinstance(type_hints.get(parameter), Parameter):
                parameters.append(parameter)
                parameters_explanation[parameter] = type_hints[parameter].description
        docstrings = textwrap.dedent(func.__doc__ or "").strip()
        return Tool(
            name=func.__name__ or kwargs.get("name", ""),
            parameters=parameters,
            parameters_explanation=parameters_explanation,
            function=func,
            description=docstrings,
        )
    return decorator

def build_tool_call_handler(tools: list[Tool]):
    def handle_tool_call(function_call: AnthropicFunctionCall, **kwargs):
        for tool in tools:
            if function_call.function_name == tool.name:
                for param in tool.parameters:
                    if param not in function_call.function_parameters:
                        return f"ERROR\n\nThe {param} parameter is missing from the function call."
                function_kwargs = {
                    **{k: v.strip() if isinstance(v, str) else v for k, v in function_call.function_parameters.items()},
                }
                param_names = tool.function.__code__.co_varnames[: tool.function.__code__.co_argcount]
                for kwarg in kwargs:
                    if kwarg in param_names:
                        function_kwargs[kwarg] = kwargs[kwarg]
                return tool(**function_kwargs)
        else:
            return "ERROR\n\nInvalid tool name. Must be one of the following: " + ", ".join([tool.name for tool in tools])
    return handle_tool_call


def parse_function_calls(response_contents: str, tools: list[Tool]) -> list[dict[str, str]]:
    tool_call_parameters = {tool.name: tool.parameters for tool in tools}
    tool_calls = []
    # first get all tool calls
    for tool_name in tool_call_parameters.keys():
        tool_call_regex = rf'<{tool_name}>(?P<function_call>.*?)<\/{tool_name}>'
        tool_call_matches = re.finditer(tool_call_regex, response_contents, re.DOTALL)
        # now we extract its parameters
        for tool_call_match in tool_call_matches:
            tool_call_contents = tool_call_match.group("function_call")
            # get parameters based off of tool name
            parameters = tool_call_parameters[tool_name]
            tool_call = { "tool": tool_name, 
                        "arguments": parse_function_call_parameters(tool_call_contents, parameters) 
                        }
            tool_calls.append(tool_call)
    return tool_calls

def validate_and_parse_function_call(
    function_calls_string: str, chat_gpt: ChatGPT, tools: list[Tool]
) -> AnthropicFunctionCall:
    function_calls = parse_function_calls(
        function_calls_string.strip("\n") + "\n</function_call>",
        tools
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
