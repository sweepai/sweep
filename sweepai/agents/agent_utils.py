# ensure that all additional_messages are 32768 characters at most, if not split them
from dataclasses import dataclass
import textwrap
from typing import Callable
from sweepai.core.entities import Message
from typing import get_type_hints

from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall

MAX_CHARS = 32000

def ensure_additional_messages_length(additional_messages: list[Message]) -> list[Message]:
    for i, additional_message in enumerate(additional_messages):
        if len(additional_message.content) > MAX_CHARS:
            wrapper = textwrap.TextWrapper(width=MAX_CHARS, replace_whitespace=False)
            new_messages = wrapper.wrap(additional_message.content)
            # replace the original message with the broken up messages
            for j, new_message in enumerate(new_messages):
                if j == 0:
                    additional_messages[i] = Message(
                        role=additional_message.role,
                        content=new_message,
                    )
                else:
                    additional_messages.insert(
                        i + j,
                        Message(
                            role=additional_message.role,
                            content=new_message,
                        ),
                    )
    return additional_messages

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

if __name__ == "__main__":
    @tool(name="test", description="test", parameters=["test"])
    def test(test):
        return test

    print(test("test"))
