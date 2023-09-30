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


# We are using the jedi parsing to get the type of the variable at a paricular
# code location
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
                # If the module is native to python its not present in
                # site-packages but rather in the python/ folder
                # so we are gating against all things python for now
                # if one of our clients has a problem we fix it later
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
                # If this is a class we are looking at, lets try to infer the
                # type instead of doing goto def because import styles can
                # give us a wrong idea about what the codelocation is
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

        # Create a script for the code.
        script = jedi.Script(code, project=self.jedi_project)
        try:
            data = script.goto(line=line, column=column)
            if len(data) == 0:
                return None
            else:
                return data[0].full_name
        except Exception:
            # print("JEDI Exception", str(e), full_file_path, line, column)
            return None

    def get_full_type_at_location(
        self,
        file_path: str,
        line: int,
        symbol_to_search: str,
        directory_path: str,
        # We return the full type at the location if present and the scope at
        # the location and the column number
    ) -> Optional[Tuple[str, str, int]]:
        module_name = file_path.replace(directory_path, "", 1)[:-3].replace("/", ".")
        code = ""
        with open(file_path, "r") as code_file:
            code = code_file.read()
        script = jedi.Script(code, project=self.jedi_project)
        code_lines = code.split("\n")
        line_at_location = code_lines[line - 1]
        # Now we need to the column at which the symbol is located
        # We are going to do a simple search for the symbol in the line
        # and then get the column at which it is located
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
            # Here we are going to split the code snippet and find the symbol
            # and which line it exists on and then update the line number
            code_snippet_parts = code_snippet.split("\n")
            for code_snippet_part in code_snippet_parts:
                if symbol_to_search in code_snippet_part:
                    line = line + code_snippet_parts.index(code_snippet_part)
                    break
        # We are going to break down the task in the following steps:
        # - first we get the type at the location for the symbol
        # - next we rg through the codebase for this symbol
        # - we filter for the hits which are of the same type as the current symbol
        # - we return the references
        code = ""
        with open(file_path, "r") as code_file:
            code = code_file.read()
        script = jedi.Script(code, project=self.jedi_project)
        code_lines = code.split("\n")
        line_at_location = code_lines[line - 1]
        # Now we need to the column at which the symbol is located
        # We are going to do a simple search for the symbol in the line
        # and then get the column at which it is located
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

        # Now we are done with the first step, which is getting the type at the
        # location, next we will use `rg` to get the references
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
        # Now that we know the line numbers and the file locations we want
        # to look at, we can check if the types at these locations is the one
        # we are interested in
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
        # We are returning the symbol to the type mapping
    ) -> Dict[str, str]:
        module_name = file_path.replace(directory_path, "", 1)[:-3].replace("/", ".")
        code_symbol_to_type: Dict[str, str] = {}
        current_node_start_line = code_graph_node.code_location.line_start.line
        current_node_code_snippet = code_graph_node.get_raw_code()
        if current_node_code_snippet is None:
            return None

        # Now for the symbols we want to have the type for, we need to find their
        # line number and column location in the code snippet text
        code_snippet_lines = current_node_code_snippet.split("\n")
        # We want both the line number, column number here
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

        # Now we have both the line and column location for the symbols
        # we can simply ask jedi for the type for these
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


# if __name__ == "__main__":
#     directory_location = "/Users/skcd/scratch/anton/"
#     jedi_parsing = JediParsing(
#         directory_location="/Users/skcd/scratch/anton/",
#     )
#     file_path = (
#         "/Users/skcd/scratch/anton/anton/code_graph/commit_generation/search_based.py"
#     )
#     code = ""
#     with open(file_path, "r") as code_file:
#         code = code_file.read()
#     jedi_script = jedi.Script(code, project=jedi_parsing.jedi_project)
#     print(
#         jedi_parsing.get_full_inference_name_and_type(
#             full_file_path=file_path,
#             line=174,
#             column=30,
#         )
#     )
#     print(jedi_script.infer(line=174, column=30))
#     print("======")
#     print(
#         jedi_parsing.get_full_inference_name_and_type(
#             full_file_path=file_path,
#             line=180,
#             column=49,
#         )
#     )
#     print(jedi_script.infer(line=180, column=49))

# if __name__ == "__main__":
#     directory_location = "/Users/skcd/scratch/anton/"
#     jedi_parsing = JediParsing(
#         directory_location="/Users/skcd/scratch/anton/",
#     )
#     symbol_to_search = "generate_response_from_gpt4_with_messages"
#     file_path = "/Users/skcd/scratch/anton/anton/llm/openai_helper.py"
#     line_number = 74
#     references = jedi_parsing.get_references_at_location(
#         file_path=file_path,
#         line=line_number,
#         symbol_to_search=symbol_to_search,
#     )
#     print(references)

#     # Next we will try at the origin and see if we can get the references
#     file_path = "/Users/skcd/scratch/anton/anton/llm/openai_helper.py"
#     print(file_path.strip(directory_location))
#     module_name = file_path.replace(directory_location, "", 1)[:-3].replace("/", ".")
#     print(module_name)
#     line_number = 79
#     import asyncio

#     loop = asyncio.get_event_loop()
#     references = loop.run_until_complete(
#         jedi_parsing.get_references_at_location(
#             file_path=file_path,
#             line=line_number,
#             symbol_to_search=symbol_to_search,
#             module_name_for_path=module_name,
#         )
#     )
#     for reference in references:
#         print(references)


# if __name__ == "__main__":
#     jedi_parsing = JediParsing(
#         directory_location="/Users/skcd/scratch/anton/",
#     )
#     full_inference_types = jedi_parsing.get_full_inference_name_and_type(
#         full_file_path="/Users/skcd/scratch/anton/anton/parse_repo/jedi_python.py",
#         line=53,
#         column=21,
#     )
#     print(full_inference_types)
#     file_path = "/Users/skcd/scratch/anton/anton/parse_repo/jedi_python.py"
#     script = jedi.Script(
#         path=file_path,
#         project=jedi_parsing.jedi_project,
#     )
#     references = script.get_references(line=53, column=21)
#     print(references)
# print(full_inference_types)
# full_inferred_type = jedi_parsing.get_full_inferred_type(
#     full_file_path='/Users/skcd/langchain_gh/langchain/agents/self_ask_with_search/base.py',
#     line=85,
#     column=44,
# )
# function_calls = jedi_parsing.get_function_calls_in_context(
#     code_context="        agent = SelfAskWithSearchAgent.from_llm_and_tools(llm, [search_tool])",
#     file_path="/Users/skcd/langchain_gh/langchain/agents/self_ask_with_search/base.py",
# )
# print(function_calls)
# print(full_inferred_type)
