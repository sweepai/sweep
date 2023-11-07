import ast
import os
import sys
import jedi
from jedi.api.classes import Name

BUILTIN_MODULES = [builtin_module_name.strip("_") for builtin_module_name in sys.builtin_module_names] + ["builtins"]
project_dir = "sweepai"
file_name = "/api.py"
min_line = 101
max_line = 110

file_full_path = f"{project_dir}/{file_name}"

file_contents = open(file_full_path).read()


def print_function_source_code():
    project_absolute_path = os.path.abspath(project_dir)

    project = jedi.Project(path=project_absolute_path)
    script = jedi.Script(file_contents, path=file_name, project=project)
    tree = ast.parse(file_contents)
    return script, tree

script, tree = print_function_source_code()

function_definitions: set[Name] = set()


def collect_function_definitions():
    for node in ast.walk(tree):
        if node.__class__.__name__ == 'Call':
            if not min_line <= node.lineno <= max_line:
                continue
            new_function_definitions = script.goto(
                node.lineno, 
                node.col_offset,
                follow_imports=True,
                follow_builtin_imports=True,
            )
            for function_definition in new_function_definitions:
                if function_definition.full_name and any(function_definition.full_name.startswith(builtin_module) for builtin_module in BUILTIN_MODULES):
                    continue
                if function_definition.type != "function" and function_definition.type != "statement":
                    continue
                function_definitions.add(function_definition)

collect_function_definitions()


def setup_jedi_project_and_parse_ast():
    for function_definition in function_definitions:
        start_line, _ = function_definition.get_definition_start_position()
        end_line, _ = function_definition.get_definition_end_position()
        if os.path.exists(function_definition.module_path):
            module_contents = open(function_definition.module_path).read()
        else:
            module_contents = open(file_full_path).read()
        print("\n".join(module_contents.split("\n")[max(0, start_line - 1): end_line]))

setup_jedi_project_and_parse_ast()
