

# ensure that all additional_messages are 32768 characters at most, if not split them
import textwrap
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