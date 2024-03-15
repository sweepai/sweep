import re

import rope.base.project
from loguru import logger
from rope.refactor.extract import ExtractMethod

from sweepai.agents.name_agent import NameBot
from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.update_prompts import (
    extract_snippets_system_prompt,
    extract_snippets_user_prompt,
)
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.jedi_utils import (
    get_all_defined_functions,
    get_references_from_defined_function,
    setup_jedi_for_file,
)
from sweepai.utils.refactor_utils import get_refactor_snippets
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


def count_plus_minus_in_diff(description):
    plus_count = sum([1 for line in description.split("\n") if line.startswith("+")])
    minus_count = sum([1 for line in description.split("\n") if line.startswith("-")])
    return plus_count, minus_count


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
        import pdb

        pdb.set_trace()
        extractor = ExtractMethod(project, resource, start, end)
        change_set = extractor.get_changes(method_name, similar=True)

        for change in change_set.changes:
            if change.old_contents is not None:
                change.old_contents = deserialize(change.old_contents)
            else:
                change.old_contents = deserialize(change.resource.read())
            change.new_contents = deserialize(change.new_contents)

        # adding this because the change might not replace old code.
        _, subtracted_lines = count_plus_minus_in_diff(change_set.get_description())
        if subtracted_lines <= 3:
            logger.info("Change doesn't remove code, skipping")
            return contents, []
        for change in change_set.changes:
            change.do()

        result = deserialize(resource.read())
        resource.write(result)
        return result, change_set
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        resource.write(contents)
        return contents, []


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
        # first perform manual refactoring step
        script, tree = setup_jedi_for_file(
            project_dir=cloned_repo.repo_dir,
            file_full_path=f"{cloned_repo.repo_dir}/{file_path}",
        )

        all_defined_functions = get_all_defined_functions(script=script, tree=tree)
        initial_file_contents = cloned_repo.get_file_contents(file_path=file_path)
        heuristic_based_extractions = get_refactor_snippets(
            initial_file_contents, {}
        )  # check heuristics
        if len(heuristic_based_extractions) > 0:
            # some duplicated code here
            deduped_exact_matches = heuristic_based_extractions  # already deduped
            new_function_names = []
            existing_names = ", ".join(
                [def_fn.name.strip("'") for def_fn in all_defined_functions]
            )
            offset = 5
            for idx in range(0, len(deduped_exact_matches), offset):
                num_snippets = min(len(deduped_exact_matches), idx + offset) - idx
                formatted_snippets = "\n".join(
                    [
                        f"<function_to_name>\n{snippet}\n</function_to_name>"
                        for snippet in deduped_exact_matches[idx : idx + num_snippets]
                    ]
                )
                new_function_names.extend(
                    NameBot(chat_logger=self.chat_logger).name_functions(
                        old_code=cloned_repo.get_file_contents(file_path),
                        snippets=formatted_snippets,
                        existing_names=existing_names,
                        count=num_snippets,
                    )
                )
            for idx, extracted_original_code in enumerate(deduped_exact_matches):
                if idx >= len(new_function_names):
                    break
                new_code, _ = extract_method(
                    extracted_original_code,
                    file_path,
                    new_function_names[idx],
                    project_name=cloned_repo.repo_dir,
                )

        self.messages = [
            Message(
                role="system",
                content=extract_snippets_system_prompt,
                key="system",
            )
        ]
        self.messages.extend(additional_messages)
        new_code = None
        extracted_exact_matches = []
        new_function_names = []
        for fn_def in all_defined_functions:
            full_file_code = cloned_repo.get_file_contents(file_path)
            script, tree = setup_jedi_for_file(
                project_dir=cloned_repo.repo_dir,
                file_full_path=f"{cloned_repo.repo_dir}/{file_path}",
            )
            function_and_reference = get_references_from_defined_function(
                fn_def,
                script,
                tree,
                f"{cloned_repo.repo_dir}/{file_path}",
                full_file_code,
            )
            if function_and_reference.function_code.count("\n") < 20:
                continue
            # everything below must operate in a loop
            recent_file_contents = cloned_repo.get_file_contents(file_path=file_path)
            code = function_and_reference.serialize(tag="function_to_refactor")
            extract_response = self.chat(
                extract_snippets_user_prompt.format(
                    code=code,
                    file_path=file_path,
                    snippets=snippets_str,
                    changes_made=changes_made,
                )
            )
            self.messages = self.messages[:-2]
            new_function_pattern = r"<new_function_names>\s+(?P<new_function_names>.*?)</new_function_names>"
            new_function_matches = list(
                re.finditer(new_function_pattern, extract_response, re.DOTALL)
            )
            for match_ in new_function_matches:
                match = match_.groupdict()
                new_function_matches = match["new_function_names"]
                new_function_matches = new_function_matches.split("\n")
            extracted_pattern = r"<<<<<<<\s+EXTRACT\s+(?P<updated_code>.*?)>>>>>>>"
            extract_matches = list(
                re.finditer(extracted_pattern, extract_response, re.DOTALL)
            )
            new_code = None
            for idx, match_ in enumerate(extract_matches[::-1]):
                match = match_.groupdict()
                updated_code = match["updated_code"]
                updated_code = updated_code.strip("\n")
                if len(updated_code) < 150:  # too few characters
                    continue
                # too close to function length, just skip for now
                if (
                    len(updated_code) / (len(function_and_reference.function_code) + 1)
                    > 0.9
                ):
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
                matched_lines = recent_file_contents.split("\n")[
                    best_match.start : best_match.end
                ]
                # handle return edge case
                if matched_lines[-1].strip().startswith("return"):
                    matched_lines = matched_lines[:-1]
                extracted_original_code = "\n".join(matched_lines)
                extracted_exact_matches.append(extracted_original_code)
        deduped_exact_matches = []
        for extracted_exact_match in extracted_exact_matches:
            if extracted_exact_match not in deduped_exact_matches:
                deduped_exact_matches.append(extracted_exact_match)

        new_function_names = []
        existing_names = ", ".join(
            [def_fn.name.strip("'") for def_fn in all_defined_functions]
        )
        offset = 5
        for idx in range(0, len(deduped_exact_matches), offset):
            num_snippets = min(len(deduped_exact_matches), idx + offset) - idx
            formatted_snippets = "\n".join(
                [
                    f"<function_to_name>\n{snippet}\n</function_to_name>"
                    for snippet in deduped_exact_matches[idx : idx + num_snippets]
                ]
            )
            new_function_names.extend(
                NameBot(chat_logger=self.chat_logger).name_functions(
                    old_code=cloned_repo.get_file_contents(file_path),
                    snippets=formatted_snippets,
                    existing_names=existing_names,
                    count=num_snippets,
                )
            )
        for idx, extracted_original_code in enumerate(deduped_exact_matches):
            if idx >= len(new_function_names):
                break
            new_code, _ = extract_method(
                extracted_original_code,
                file_path,
                new_function_names[idx],
                project_name=cloned_repo.repo_dir,
            )
        return new_code
