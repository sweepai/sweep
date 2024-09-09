import json
import unittest

from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)

from sweepai.agents.assistant_wrapper import fix_tool_calls

if __name__ == "__main__":
    tool_call = ChatCompletionMessageToolCall(
        id="tool_call_id",
        function=Function(
            arguments="arguments",
            name="function_name",
        ),
        type="function",
    )


class TestFixToolCalls(unittest.TestCase):
    def test_multiple_tool_calls(self):
        # Setup input with multiple tool calls, including more than one 'parallel' tool calls
        input_tool_calls = [
            ChatCompletionMessageToolCall(
                id="1",
                type="function",
                function={
                    "name": "parallel",
                    "arguments": json.dumps(
                        {
                            "tool_uses": [
                                {
                                    "recipient_name": "functions.example_function",
                                    "parameters": {"arg1": "value1"},
                                },
                                {
                                    "recipient_name": "functions.example_function",
                                    "parameters": {"arg1": "value2"},
                                },
                            ]
                        }
                    ),
                },
            ),
            ChatCompletionMessageToolCall(
                id="2",
                type="function",
                function={
                    "name": "example_tool",
                    "arguments": json.dumps({"arg2": "value2"}),
                },
            ),
            ChatCompletionMessageToolCall(
                id="3",
                type="function",
                function={
                    "name": "parallel",
                    "arguments": json.dumps(
                        {
                            "tool_uses": [
                                {
                                    "recipient_name": "functions.another_function",
                                    "parameters": {"arg3": "value3"},
                                }
                            ]
                        }
                    ),
                },
            ),
        ]

        # Expected tool calls after fix
        expected_tool_calls = [
            ChatCompletionMessageToolCall(
                id="1_0",
                type="function",
                function={
                    "name": "example_function",
                    "arguments": json.dumps({"arg1": "value1"}),
                },
            ),
            ChatCompletionMessageToolCall(
                id="1_1",
                type="function",
                function={
                    "name": "example_function",
                    "arguments": json.dumps({"arg1": "value2"}),
                },
            ),
            ChatCompletionMessageToolCall(
                id="2",
                type="function",
                function={
                    "name": "example_tool",
                    "arguments": json.dumps({"arg2": "value2"}),
                },
            ),
            ChatCompletionMessageToolCall(
                id="3_0",
                type="function",
                function={
                    "name": "another_function",
                    "arguments": json.dumps({"arg3": "value3"}),
                },
            ),
        ]

        # Run the fix_tool_calls function
        output_tool_calls = fix_tool_calls(input_tool_calls)
        self.assertEqual(len(output_tool_calls), len(expected_tool_calls))
        for actual, expected in zip(output_tool_calls, expected_tool_calls):
            self.assertEqual(actual.id, expected.id)
            self.assertEqual(actual.type, expected.type)
            self.assertEqual(actual.function, expected.function)


if __name__ == "__main__":
    unittest.main()
