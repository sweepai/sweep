import ast
import os
import sys
from dataclasses import dataclass

import jedi
from jedi.api.classes import Name

BUILTIN_MODULES = [
    builtin_module_name.strip("_") for builtin_module_name in sys.builtin_module_names
] + ["builtins"]


@dataclass
class FunctionAndReferences:
    function_name: str
    function_code: str
    function_definition: Name
    indices_and_references: list[tuple[int, int, str]]

    def serialize(self, tag="function_to_refactor"):
        res = "<function_dependencies>\n"
        for _, _, reference in self.indices_and_references:
            res += f"{reference}\n\n"
        res += "</function_dependencies>\n"
        res += f"<{tag}>\n{self.function_code}\n</{tag}>"
        return res


def setup_jedi_for_file(project_dir: str, file_full_path: str):
    file_contents = open(file_full_path).read()
    project_absolute_path = os.path.abspath(project_dir)

    project = jedi.Project(path=project_absolute_path)
    script = jedi.Script(file_contents, path=file_full_path, project=project)
    tree = ast.parse(file_contents)
    return script, tree


def collect_function_definitions(
    script: jedi.Script, tree: ast.Module, min_line=0, max_line=None
):
    function_definitions: set[Name] = set()
    names = script.get_names()
    # handles class functions (only depth 1)
    classes = [name for name in names if name.type == "class"]
    for name in classes:
        class_defined_names = name.defined_names()
        for class_defined_name in class_defined_names:
            if class_defined_name.type == "function":
                function_definitions.add(class_defined_name)
    # handles all other functions
    for node in ast.walk(tree):
        if node.__class__.__name__ == "Call":
            if max_line and not min_line <= node.lineno <= max_line:
                continue
            new_function_definitions: list[Name] = script.goto(
                node.lineno,
                node.col_offset,
                follow_imports=True,
                follow_builtin_imports=True,
            )
            for function_definition in new_function_definitions:
                # print(function_definition.type)
                # print(function_definition.full_name)
                if "site-packages" in str(function_definition.module_path):
                    continue
                if function_definition.full_name and any(
                    function_definition.full_name.startswith(builtin_module)
                    for builtin_module in BUILTIN_MODULES
                ):
                    continue
                if (
                    function_definition.type != "function"
                ):
                    continue
                function_definitions.add(function_definition)
    return function_definitions


def get_function_references(function_definition: Name, file_full_path: str):
    start_line, _ = function_definition.get_definition_start_position()
    end_line, _ = function_definition.get_definition_end_position()
    if os.path.exists(function_definition.module_path):
        module_contents = open(function_definition.module_path).read()
    else:
        module_contents = open(file_full_path).read()
    return (
        start_line,
        end_line,
        "\n".join(module_contents.split("\n")[max(0, start_line - 1) : end_line]),
    )


# the modifications affect eachother so make sure it's in a loop
def get_all_defined_functions(script: jedi.Script, tree: ast.Module):
    function_definitions = collect_function_definitions(script=script, tree=tree)
    # filter out function definitions that are not in the original file
    function_definitions = [
        fn_def
        for fn_def in function_definitions
        if fn_def.module_name == script.get_context().module_name
    ]
    return function_definitions


# this function cannot depend on the line no
def get_references_from_defined_function(
    fn_def: Name,
    script: jedi.Script,
    tree: ast.Module,
    file_full_path: str,
    full_file_code: str,
):
    # may fail if it's not present but this shouldn't happen
    fn_def = script.search(fn_def.name, all_scopes=True)[0]
    start_line = max(0, (fn_def.get_definition_start_position()[0] - 1))
    end_line = fn_def.get_definition_end_position()[0]
    function_code = "\n".join(full_file_code.split("\n")[start_line:end_line])
    sub_function_definitions = collect_function_definitions(
        script=script, tree=tree, min_line=start_line, max_line=end_line
    )
    indices_and_code = []
    for sub_fn_def in sub_function_definitions:
        if sub_fn_def.full_name != fn_def.full_name:
            indices_and_code.append(get_function_references(sub_fn_def, file_full_path))
    fn_and_ref = FunctionAndReferences(
        function_name=fn_def.full_name,
        function_code=function_code,
        function_definition=fn_def,
        indices_and_references=indices_and_code,
    )
    return fn_and_ref
