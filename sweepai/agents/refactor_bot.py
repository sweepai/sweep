import re

import rope.base.project
from loguru import logger
from rope.refactor.extract import ExtractMethod

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.update_prompts import (
    extract_snippets_system_prompt,
    extract_snippets_user_prompt,
)
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.jedi_utils import get_all_defined_functions, get_references_from_defined_function, setup_jedi_for_file
from sweepai.utils.search_and_replace import find_best_match

APOSTROPHE_MARKER = "__APOSTROPHE__"
PERCENT_FORMAT_MARKER = "__PERCENT_FORMAT__"


def serialize(text: str):
    # Replace "'{var}'" with "__APOSTROPHE__{var}__APOSTROPHE__"
    text = re.sub(
        r"'{([^'}]*?)}'", f"{APOSTROPHE_MARKER}{{\\1}}{APOSTROPHE_MARKER}", text
    )
    # Replace "%s" with "__PERCENT_FORMAT__"
    text = re.sub(r"%\((.*?)\)s", f"{PERCENT_FORMAT_MARKER}{{\\1}}", text)
    return text


def deserialize(text: str):
    text = re.sub(f"{APOSTROPHE_MARKER}{{(.*?)}}{APOSTROPHE_MARKER}", "'{\\1}'", text)
    text = re.sub(f"{PERCENT_FORMAT_MARKER}{{(.*?)}}", "%(\\1)s", text)
    return text


def extract_method(
    snippet,
    file_path,
    method_name,
    project_name,
):
    project = rope.base.project.Project(project_name)

    resource = project.get_resource(file_path)
    contents = resource.read()
    serialized_contents = serialize(contents)
    resource.write(serialized_contents)

    serialized_snippet = serialize(snippet)
    start, end = serialized_contents.find(serialized_snippet), serialized_contents.find(
        serialized_snippet
    ) + len(serialized_snippet)

    try:
        extractor = ExtractMethod(project, resource, start, end)
        change_set = extractor.get_changes(method_name, similar=True)

        for change in change_set.changes:
            if change.old_contents is not None:
                change.old_contents = deserialize(change.old_contents)
            else:
                change.old_contents = deserialize(change.resource.read())
            change.new_contents = deserialize(change.new_contents)

        for change in change_set.changes:
            change.do()

        result = deserialize(resource.read())
        resource.write(result)
        return result, change_set
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        resource.write(contents)
        return contents, []


def serialize_method_name(method_name):
    # handles '1. "method_name"' -> 'method_name'
    if "." in method_name:
        return method_name.split(". ")[-1].strip('"')
    return method_name.strip().strip('"')


class RefactorBot(ChatGPT):
    def refactor_snippets(
        self,
        additional_messages: list[Message] = [],
        snippets_str="",
        file_path: str = "",
        update_snippets_code: str = "",
        request="",
        changes_made="",
        cloned_repo: ClonedRepo = None,
        **kwargs,
    ):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        self.messages = [
            Message(
                role="system",
                content=extract_snippets_system_prompt,
                key="system",
            )
        ]
        self.messages.extend(additional_messages)

        script, tree = setup_jedi_for_file(project_dir=cloned_repo.cache_dir,
            file_full_path=f"{cloned_repo.cache_dir}/{file_path}"
        )

        all_defined_functions = get_all_defined_functions(
            script=script, tree=tree
        )
        new_code = None
        change_sets = []
        for fn_def in all_defined_functions:
            full_file_code = cloned_repo.get_file_contents(file_path)
            script, tree = setup_jedi_for_file(project_dir=cloned_repo.cache_dir,
                file_full_path=f"{cloned_repo.cache_dir}/{file_path}"
            )
            function_and_reference = get_references_from_defined_function(fn_def, script, tree, f"{cloned_repo.cache_dir}/{file_path}", full_file_code)
            if function_and_reference.function_code.count("\n") < 20:
                continue
            # everything below must operate in a loop
            recent_file_contents = cloned_repo.get_file_contents(file_path=file_path)
            code = f"<original_code>\n{recent_file_contents}</original_code>\n"
            code += function_and_reference.serialize(tag="function_to_refactor")
            extract_response = self.chat(
                extract_snippets_user_prompt.format(
                    code=code,
                    file_path=file_path,
                    snippets=snippets_str,
                    changes_made=changes_made,
                )
            )
            self.messages = self.messages[:-2]
            new_function_pattern = (
                r"<new_function_names>\s+(?P<new_function_names>.*?)</new_function_names>"
            )
            new_function_matches = list(
                re.finditer(new_function_pattern, extract_response, re.DOTALL)
            )
            new_function_names = []
            for match_ in new_function_matches:
                match = match_.groupdict()
                new_function_names = match["new_function_names"]
                new_function_names = new_function_names.split("\n")
            new_function_names = [
                serialize_method_name(
                    new_function_name.strip().strip('"').strip("'").strip("`")
                )
                for new_function_name in new_function_names
                if new_function_name.strip()
            ]
            extracted_pattern = r"<<<<<<<\s+EXTRACT\s+(?P<updated_code>.*?)>>>>>>>"
            extract_matches = list(
                re.finditer(extracted_pattern, extract_response, re.DOTALL)
            )
            new_code = None
            for idx, match_ in enumerate(extract_matches[::-1]):
                match = match_.groupdict()
                updated_code = match["updated_code"]
                updated_code = updated_code.strip("\n")
                if len(updated_code) < 150:
                    continue
                best_match = find_best_match(updated_code, recent_file_contents)
                if best_match.score < 70:
                    updated_code = "\n".join(updated_code.split("\n")[1:])
                    best_match = find_best_match(updated_code, recent_file_contents)
                    if best_match.score < 80:
                        updated_code = "\n".join(updated_code.split("\n")[:-1])
                        best_match = find_best_match(updated_code, recent_file_contents)
                        if best_match.score < 80:
                            continue
                matched_lines = recent_file_contents.split("\n")[best_match.start : best_match.end]
                # handle return edge case
                if matched_lines[-1].strip().startswith("return"):
                    matched_lines = matched_lines[:-1]
                extracted_original_code = "\n".join(
                    matched_lines
                )
                new_code, change_set = extract_method(
                    extracted_original_code,
                    file_path,
                    new_function_names[idx],
                    project_name=cloned_repo.cache_dir,
                )
                change_sets.append(change_set)
        if change_sets == []:
            return new_code
        for change_set in change_sets:
            if change_set:
                for change in change_set.changes:
                    change.undo()
        return new_code