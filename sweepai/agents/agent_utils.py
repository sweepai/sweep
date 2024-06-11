# ensure that all additional_messages are 32768 characters at most, if not split them
from dataclasses import dataclass
import textwrap
from typing import Callable
from sweepai.core.entities import Message

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
class Tool:
    name: str
    parameters: list[str]
    parameters_explanation: dict[str, str]
    function: Callable

    @property
    def xml(self):
        parameters_xml = "\n".join(f"<{parameter}>\n{self.parameters_explanation[parameter]}\n</{parameter}>" for parameter in self.parameters)
        return f"""<{self.name}>
{parameters_xml}
</{self.name}>"""
    
    def __call__(self, **kwargs):
        return self.function(**kwargs)

def tool(**kwargs):
    def decorator(func):
        return Tool(
            name=func.__name__ or kwargs.get("name", ""),
            parameters=kwargs.get("parameters", []),
            parameters_explanation=kwargs.get("parameters_explanation", {}),
            function=func
        )
    return decorator

if __name__ == "__main__":
    @tool(name="test", description="test", parameters=["test"])
    def test(test):
        return test

    print(test("test"))
