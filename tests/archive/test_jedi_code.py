"""
We are going to get the type of a variable in python using the jedi library.
This will help us build a codegraph which is extremely granular where we know
exactly the callers and where they are located(makes us feature compatible
with sourcegraph in a way :V)
"""

import asyncio
import dataclasses
import importlib.util
from typing import Dict, List, Optional, Tuple

import dataclasses_json
import jedi
from anton.code_graph.type import CodeGraphNode, JediFullReturnType


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class JediReferenceInformation:
    full_type: str
    full_file_path: str
    line: int
    column: int
    scope_name: str


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class JediReferenceInformationWithCommandOutput:
    references: List[JediReferenceInformation]
    command_output: Optional[Tuple[List[str], str, str, Optional[int]]] = None



class JediParsing:
    def __init__(
        self,
        directory_location: str,
    ) -> None:
        self.directory_location = directory_location
        self.jedi_project = jedi.Project(path=directory_location)

    def get_function_calls_in_context(
        self,
        code_context: str,
        file_path: str,
    ) -> None:
        """
        Gets the function calls happening in a given context, leading to better
        understanding of the functions which are used in the code.
        """
        script = jedi.Script(
            code_context,
            path=file_path,
            project=self.jedi_project,
        )
        for node in script.get_names(
            all_scopes=True,
            definitions=True,
            references=True,
        ):
            if node.type == "function":
                print(
                    f"Function {node.full_name} is called at line {node.line} and column {node.column}::{node.get_definition_end_position()}"
                )

    def get_full_inference_name_and_type(
        self,
        full_file_path: str,
        line: int,
        column: int,
    ) -> Optional[JediFullReturnType]:
        """
        Gets the full qualified type of the variable here along with the type of
        variable call it is (class vs function)
        """
        code = ""
        with open(full_file_path, "r") as code_file:
            code = code_file.read()

        script = jedi.Script(code, project=self.jedi_project)
        try:
            data = script.goto(line=line, column=column)
            inference = script.infer(line=line, column=column)
            if len(data) == 0:
                return None
            else:
                is_external_import = False
                for inference_bits in inference:
                    try:
                        inference_type = importlib.util.find_spec(
                            inference_bits.module_name
                        )
                        if inference_type is not None:
                            is_external_import = True
                    except Exception:
                        continue
                if data[0].module_path is not None and (
                    "site-packages" in str(data[0].module_path)
                    or "python" in str(data[0].module_path)
                ):
                    is_external_import = True
                goto_definition_type = JediFullReturnType(
                    fully_qualified_type=data[0].full_name,
                    attribute_type=data[0].type,
                    is_external_library_import=is_external_import,
                    module_path=str(data[0].module_path),
                )
                if data[0].type == "class":
                    inference_list = script.infer(line=line, column=column)
                    if len(inference_list) == 0:
                        return goto_definition_type
                    else:
                        for inference in inference_list:
                            if (
                                inference.type == "class"
                                and inference.full_name is not None
                            ):
                                return JediFullReturnType(
                                    fully_qualified_type=inference.full_name,
                                    attribute_type="class",
                                    is_external_library_import=is_external_import,
                                    module_path=str(inference.module_path)
                                    if inference.module_path is not None
                                    else full_file_path,
                                )
                return goto_definition_type
        except Exception:
            return None

    def get_full_inferred_type(
        self,
        full_file_path: str,
        unique_id: str,
        line: int,
        column: int,
    ) -> Optional[str]:
        """
        Gets the full qualified type of the variable here given the code
        location
        """
        code = ""
        unique_file_path = f"{full_file_path}"
        with open(unique_file_path, "r") as code_file:
            code = code_file.read()
        script = jedi.Script(code, project=self.jedi_project)
        try:
            data = script.goto(line=line, column=column)
            if len(data) == 0:
                return None
            else:
                return data[0].full_name
        except Exception:
            return None

    def get_full_type_at_location(
        self,
        file_path: str,
        line: int,
        symbol_to_search: str,
        directory_path: str,
      
    ) -> Optional[Tuple[str, str, int]]:
        module_name = file_path.replace(directory_path, "", 1)[:-3].replace("/", ".")
        code = ""
        with open(file_path, "r") as code_file:
            code = code_file.read()
        script = jedi.Script(code, project=self.jedi_project)
        code_lines = code.split("\n")
        line_at_location = code_lines[line - 1]
        column_at_location = line_at_location.find(symbol_to_search)
        inferences = script.infer(line=line, column=column_at_location + 1)
        scope = script.get_context(
            line=line,
            column=column_at_location + 1,
        )
        if scope is None:
            return None
        if len(inferences) == 0:
            return None
        full_type = inferences[0].full_name
        if full_type.startswith("__main__"):
            full_type = full_type.replace("__main__", module_name)
        return (
            full_type,
            scope.full_name.replace("__main__", module_name),
            column_at_location + 1,
        )

    async def get_references_at_location(
        self,
        file_path: str,
        line: int,
        code_snippet: Optional[str],
        symbol_to_search: str,
        module_name_for_path: str,
    ) -> JediReferenceInformationWithCommandOutput:
        if code_snippet is not None:
           
            code_snippet_parts = code_snippet.split("\n")
            for code_snippet_part in code_snippet_parts:
                if symbol_to_search in code_snippet_part:
                    line = line + code_snippet_parts.index(code_snippet_part)
                    break
       
        code = ""
        with open(file_path, "r") as code_file:
            code = code_file.read()
        script = jedi.Script(code, project=self.jedi_project)
        code_lines = code.split("\n")
        line_at_location = code_lines[line - 1]
        column_at_location = line_at_location.find(symbol_to_search)
        type_at_location_list = script.goto(
            line=line,
            column=column_at_location + 1,
        )
        if len(type_at_location_list) == 0:
            return []
        symbol_full_type: str = type_at_location_list[0].full_name
        if symbol_full_type.startswith("__main__"):
            symbol_full_type = symbol_full_type.replace(
                "__main__", module_name_for_path
            )
        cmd = ["rg", "--json", symbol_to_search]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        stdout_parts: List[str] = stdout.decode().split("\n")

        @dataclasses_json.dataclass_json
        @dataclasses.dataclass
        class CodeLocation:
            line_number: int
            file_path: str

        code_locations_to_check: List[CodeLocation] = []
        code_symbols_which_have_same_type: List[JediReferenceInformation] = []

        for stdout_line in stdout_parts:
            import json

            if stdout_line == "":
                continue

            parsed_json = json.loads(stdout_line)
            if parsed_json["type"] == "match":
                code_locations_to_check.append(
                    CodeLocation(
                        file_path=parsed_json["data"]["path"]["text"],
                        line_number=parsed_json["data"]["line_number"],
                    )
                )

        for code_location_to_check in code_locations_to_check:
            type_with_module_name = self.get_full_type_at_location(
                file_path=code_location_to_check.file_path,
                line=code_location_to_check.line_number,
                symbol_to_search=symbol_to_search,
                directory_path=self.directory_location,
            )
            if type_with_module_name is None:
                continue
            if type_with_module_name[0] == symbol_full_type:
                code_symbols_which_have_same_type.append(
                    JediReferenceInformation(
                        full_type=type_with_module_name[0],
                        full_file_path=code_location_to_check.file_path,
                        line=code_location_to_check.line_number,
                        column=type_with_module_name[2],
                        scope_name=type_with_module_name[1],
                    )
                )
        return JediReferenceInformationWithCommandOutput(
            references=code_symbols_which_have_same_type,
            command_output=(
                cmd,
                stdout.decode(),
                stderr.decode(),
                process.returncode,
            ),
        )

    async def get_types_in_context(
        self,
        code_graph_node: CodeGraphNode,
        symbols_we_need_types_for: List[str],
        file_path: str,
        directory_path: str,
    ) -> Dict[str, str]:
        module_name = file_path.replace(directory_path, "", 1)[:-3].replace("/", ".")
        code_symbol_to_type: Dict[str, str] = {}
        current_node_start_line = code_graph_node.code_location.line_start.line
        current_node_code_snippet = code_graph_node.get_raw_code()
        if current_node_code_snippet is None:
            return None
        code_snippet_lines = current_node_code_snippet.split("\n")
        symbol_to_line_number: Dict[str, Tuple[int, int]] = {}
        for symbol in symbols_we_need_types_for:
            for code_snippet_line in code_snippet_lines:
                if symbol in code_snippet_line:
                    line_number = current_node_start_line + code_snippet_lines.index(
                        code_snippet_line
                    )
                    column_number = code_snippet_line.find(symbol)
                    symbol_to_line_number[symbol] = (line_number, column_number + 1)
                    break
        for symbol, line_number_and_column_number in symbol_to_line_number.items():
            full_type = self.get_full_inferred_type(
                full_file_path=code_graph_node.code_location.file_name,
                unique_id=code_graph_node.id,
                line=line_number_and_column_number[0],
                column=line_number_and_column_number[1],
            )
            if full_type is None:
                continue
            fixed_full_type = full_type.replace("__main__", module_name)
            code_symbol_to_type[symbol] = fixed_full_type
        return code_symbol_to_type


