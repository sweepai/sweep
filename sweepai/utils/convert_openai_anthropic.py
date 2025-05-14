from __future__ import annotations
from dataclasses import dataclass
import re


def convert_openai_function_to_anthropic_prompt(function: dict) -> str:
    unformatted_prompt = """<tool_description>
<tool_name>{tool_name}</tool_name>
<description>
{description}
</description>
<parameters>
{parameters}
</parameters>
</tool_description>"""
    unformatted_parameter = """<parameter>
<name>{parameter_name}</name>
<type>{parameter_type}</type>
<description>{parameter_description}</description>
</parameter>"""
    parameters_strings = []
    
    for parameter_name, parameter_dict in function["parameters"]["properties"].items():
        parameters_strings.append(unformatted_parameter.format(
            parameter_name=parameter_name,
            parameter_type=parameter_dict["type"],
            parameter_description=parameter_dict["description"],
        ))
    return unformatted_prompt.format(
        tool_name=function["name"],
        description=function["description"],
        parameters="\n".join(parameters_strings),
    )

def convert_all_functions(functions: list) -> str:
    # convert all openai functions to print anthropic prompt
    for function in functions:
        print(convert_openai_function_to_anthropic_prompt(function))

@dataclass
class AnthropicFunctionCall:
    function_name: str
    function_parameters: dict[str, str]

    def to_string(self) -> str:
        function_call_string = "<invoke>\n"
        function_call_string += f"<tool_name>{self.function_name}</tool_name>\n"
        function_call_string += "<parameters>\n"
        for param_name, param_value in self.function_parameters.items():
            function_call_string += f"<{param_name}>\n{param_value}\n</{param_name}>\n"
        function_call_string += "</parameters>\n"
        function_call_string += "</invoke>"
        return function_call_string

    @staticmethod
    def mock_function_calls_from_string(function_calls_string: str) -> list[AnthropicFunctionCall]:
        function_calls = []

        # Regular expression patterns
        function_name_pattern = r'<tool_name>(.*?)</tool_name>'
        parameters_pattern = r'<parameters>(.*?)</parameters>'
        parameter_pattern = r'<(.*?)>(.*?)<\/\1>'
        
        # Extract function calls
        function_call_matches = re.findall(r'<invoke>(.*?)</invoke>', function_calls_string, re.DOTALL)
        for function_call_match in function_call_matches:
            # Extract function name
            function_name_match = re.search(function_name_pattern, function_call_match)
            function_name = function_name_match.group(1) if function_name_match else None

            # Extract parameters section
            parameters_match = re.search(parameters_pattern, function_call_match, re.DOTALL)
            parameters_section = parameters_match.group(1) if parameters_match else ''

            # Extract parameters within the parameters section
            parameter_matches = re.findall(parameter_pattern, parameters_section, re.DOTALL)
            function_parameters = {}
            for param in parameter_matches:
                parameter_name = param[0]
                parameter_value = param[1]
                function_parameters[parameter_name] = parameter_value.strip("\n")

            if function_name and function_parameters != {}:
                function_calls.append(AnthropicFunctionCall(function_name, function_parameters))

        return function_calls

def mock_function_calls_to_string(function_calls: list[AnthropicFunctionCall]) -> str:
    function_calls_string = "<function_call>\n"
    for function_call in function_calls:
        function_calls_string += function_call.to_string() + "\n"
    function_calls_string += "</function_call>"
    return function_calls_string

if __name__ == "__main__":    
    test_str = """<function_call>
<invoke>
<tool_name>submit_report_and_plan</tool_name>
<parameters>
<report>
The main API implementation for the Sweep application is in the `sweepai/api.py` file. This file handles various GitHub events, such as pull requests, issues, and comments, and triggers corresponding actions.

The `PRChangeRequest` class, defined in the `sweepai/core/entities.py` file, is used to encapsulate information about a pull request change, such as the comment, repository, and user information. This class is utilized throughout the `sweepai/api.py` file to process and respond to the different GitHub events.

To solve the user request, the following plan should be followed:

1. Carefully review the `sweepai/api.py` file to understand how the different GitHub events are handled and the corresponding actions that are triggered.
2. Analyze the usage of the `PRChangeRequest` class in the `sweepai/api.py` file to understand how it is used to process pull request changes.
3. Determine the specific issue or feature that needs to be implemented or fixed based on the user request.
4. Implement the necessary changes in the `sweepai/api.py` file, utilizing the `PRChangeRequest` class as needed.
5. Ensure that the changes are thoroughly tested and that all relevant cases are covered.
6. Submit the changes for review and deployment.
</report>
<plan>
1. Review the `sweepai/api.py` file to understand the overall structure and flow of the application, focusing on how GitHub events are handled and the corresponding actions that are triggered.
2. Analyze the usage of the `PRChangeRequest` class in the `sweepai/api.py` file to understand how it is used to process pull request changes, including the information it encapsulates and the various methods that operate on it.
3. Determine the specific issue or feature that needs to be implemented or fixed based on the user request. This may involve identifying the relevant GitHub event handlers and the corresponding logic that needs to be modified.
4. Implement the necessary changes in the `sweepai/api.py` file, utilizing the `PRChangeRequest` class as needed to process the pull request changes. This may include adding new event handlers, modifying existing ones, or enhancing the functionality of the `PRChangeRequest` class.
5. Thoroughly test the changes to ensure that all relevant cases are covered, including edge cases and error handling. This may involve writing additional unit tests or integration tests to validate the functionality.
6. Once the changes have been implemented and tested, submit the modified `sweepai/api.py` file for review and deployment.
</plan>
</parameters>
</invoke>
</function_call>"""

    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(test_str)
    for function_call in function_calls:
        print(function_call)
        print(function_call.to_string())
    print(mock_function_calls_to_string(function_calls))