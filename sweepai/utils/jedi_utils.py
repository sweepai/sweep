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
            reference_lines = reference.split("\n")
            if len(reference_lines) > 50:
                selected_lines = reference_lines[:12] + ["..."] + reference_lines[-12:]
                reference = "\n".join(selected_lines)
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
    functions = [name for name in names if name.type == "function"]
    package_prefix = script.get_context().module_name.split(".")[0]
    for name in functions:
        function_definitions.add(name)
    
    function_definitions = list(function_definitions)
    filtered_definitions = []
    for name in function_definitions:
        if not name.full_name.startswith(package_prefix):
            continue
        if "site-packages" in str(name.module_path):
            continue
        if name.full_name and any(
                    name.full_name.startswith(builtin_module)
                    for builtin_module in BUILTIN_MODULES
            ):
            continue
        filtered_definitions.append(name)
    # used for getting only the functions within a span of lines
    if min_line and max_line:
        code_span = "\n".join(open(script.path).read().split("\n")[min_line:max_line])
        filtered_definitions = [
            fn_def
            for fn_def in filtered_definitions
            if f"{fn_def.name}(" in code_span
        ]
    return filtered_definitions


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
        if fn_def.full_name.startswith(script.get_context().module_name)
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
    filtered_definitions = []
    package_prefix = script.get_context().module_name.split(".")[0]
    for sub_fn_def in sub_function_definitions: 
        # filter out non-local functions
        if not sub_fn_def.full_name or not sub_fn_def.name:
            continue
        if not sub_fn_def.full_name.startswith(package_prefix):
            continue
        # filter out __init__ functions
        if sub_fn_def.name.endswith("__") and sub_fn_def.name.startswith("__"):
            continue
        if sub_fn_def.full_name == fn_def.full_name:
            continue
        filtered_definitions.append(sub_fn_def)
    for sub_fn_def in filtered_definitions:
        indices_and_code.append(get_function_references(sub_fn_def, file_full_path))
    fn_and_ref = FunctionAndReferences(
        function_name=fn_def.full_name,
        function_code=function_code,
        function_definition=fn_def,
        indices_and_references=indices_and_code,
    )
    return fn_and_ref


if __name__ == "__main__":
    script, tree = setup_jedi_for_file(
        project_dir="tests/notebooks/src/",
        file_full_path="tests/notebooks/src/test.py",
    )
    all_defined_functions = get_all_defined_functions(script=script, tree=tree)