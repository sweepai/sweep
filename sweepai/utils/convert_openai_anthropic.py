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
class MockFunctionCall:
    function_name: str
    function_parameters: dict[str, str]

    @staticmethod
    def mock_function_calls_from_string(function_calls_string: str) -> list[MockFunctionCall]:
        function_calls = []

        # Regular expression patterns
        function_name_pattern = r'<tool_name>(.*?)</tool_name>'
        parameters_pattern = r'<parameters>(.*?)</parameters>'
        parameter_pattern = r'<(.*?)>(.*?)</\1>'
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
            parameter_matches = re.findall(parameter_pattern, parameters_section)
            function_parameters = {}
            for param in parameter_matches:
                parameter_name = param[0]
                parameter_value = param[1]
                function_parameters[parameter_name] = parameter_value

            if function_name:
                function_calls.append(MockFunctionCall(function_name, function_parameters))

        return function_calls