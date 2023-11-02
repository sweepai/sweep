import re

import rope.base.project
from loguru import logger
from rope.refactor.extract import ExtractMethod

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.core.update_prompts import (
    extract_snippets_system_prompt,
    extract_snippets_user_prompt,
)
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.search_and_replace import find_best_match

APOSTROPHE_MARKER = "__APOSTROPHE__"


def serialize(text: str):
    # Replace "'{var}'" with "__APOSTROPHE__{var}__APOSTROPHE__"
    return re.sub(r"'(.*?)'", f"{APOSTROPHE_MARKER}\\1{APOSTROPHE_MARKER}", text)


def deserialize(text: str):
    return re.sub(f"{APOSTROPHE_MARKER}(.*?){APOSTROPHE_MARKER}", "'\\1'", text)


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
        change_set = extractor.get_changes(method_name, global_=True)

        for change in change_set.changes:
            if change.old_contents is not None:
                change.old_contents = deserialize(change.old_contents)
            else:
                change.old_contents = deserialize(change.resource.read())
            change.new_contents = deserialize(change.new_contents)

        for change in change_set.changes:
            change.do()

        result = deserialize(resource.read())
        return result, change_set
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        resource.write(contents)
        raise e


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
            "gpt-4-32k-0613"
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else "gpt-3.5-turbo-16k-0613"
        )
        self.messages = [
            Message(
                role="system",
                content=extract_snippets_system_prompt,
                key="system",
            )
        ]
        self.messages.extend(additional_messages)
        extract_response = self.chat(
            extract_snippets_user_prompt.format(
                code=update_snippets_code,
                file_path=file_path,
                snippets=snippets_str,
                request=request,
                changes_made=changes_made,
            )
        )
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
            new_function_name.strip().strip('"').strip("'").strip("`")
            for new_function_name in new_function_names
            if new_function_name.strip()
        ]
        extracted_pattern = r"<<<<<<<\s+EXTRACT\s+(?P<updated_code>.*?)>>>>>>>"
        extract_matches = list(
            re.finditer(extracted_pattern, extract_response, re.DOTALL)
        )
        change_sets = []
        new_code = None
        for idx, match_ in enumerate(extract_matches):
            match = match_.groupdict()
            updated_code = match["updated_code"]
            updated_code = updated_code.strip("\n")
            best_match = find_best_match(updated_code, snippets_str)
            if best_match.score < 70:
                updated_code = "\n".join(updated_code.split("\n")[1:])
                best_match = find_best_match(updated_code, snippets_str)
                if best_match.score < 80:
                    updated_code = "\n".join(updated_code.split("\n")[:-1])
                    best_match = find_best_match(updated_code, snippets_str)
                    if best_match.score < 80:
                        continue
            extracted_original_code = "\n".join(
                snippets_str.split("\n")[best_match.start : best_match.end]
            )
            new_code, change_set = extract_method(
                extracted_original_code,
                file_path,
                new_function_names[idx],
                project_name=cloned_repo.cache_dir,
            )
            change_sets.append(change_set)
        for change_set in change_sets:
            for change in change_set.changes:
                change.undo()
        return new_code


if __name__ == "__main__":
    additional_messages = [
        Message(
            role="user",
            content="""Repo: sweep: Sweep: AI-powered Junior Developer for small features and bug fixes.
Issue Title: refactor vector_db.py by pulling common functions and patterns out and putting them in the same function
Issue Description: ### Details

_No response_""",
            key="user",
        )
    ]
    snippets_str = """\
<snippet index="0">
def compute_deeplake_vs(collection_name, documents, ids, metadatas, sha):
    if len(documents) > 0:
        logger.info(f"Computing embeddings with {VECTOR_EMBEDDING_SOURCE}...")
        # Check cache here for all documents
        embeddings = [None] * len(documents)
        if redis_client:
            cache_keys = [
                hash_sha256(doc)
                + SENTENCE_TRANSFORMERS_MODEL
                + VECTOR_EMBEDDING_SOURCE
                + CACHE_VERSION
                for doc in documents
            ]
            cache_values = redis_client.mget(cache_keys)
            for idx, value in enumerate(cache_values):
                if value is not None:
                    arr = json.loads(value)
                    if isinstance(arr, list):
                        embeddings[idx] = np.array(arr, dtype=np.float32)
        logger.info(
            f"Found {len([x for x in embeddings if x is not None])} embeddings in cache"
        )
        indices_to_compute = [idx for idx, x in enumerate(embeddings) if x is None]
        documents_to_compute = [documents[idx] for idx in indices_to_compute]
        logger.info(f"Computing {len(documents_to_compute)} embeddings...")
        computed_embeddings = embedding_function(documents_to_compute)
        logger.info(f"Computed {len(computed_embeddings)} embeddings")

        for idx, embedding in zip(indices_to_compute, computed_embeddings):
            embeddings[idx] = embedding

        try:
            embeddings = np.array(embeddings, dtype=np.float32)
        except SystemExit:
            raise SystemExit
        except:
            logger.exception(
                "Failed to convert embeddings to numpy array, recomputing all of them"
            )
            embeddings = embedding_function(documents)
            embeddings = np.array(embeddings, dtype=np.float32)
</snippet>
"""
    file_path = "sweepai/core/vector_db.py"
    request = "Break this function into smaller sub-functions"
    changes_made = ""
    bot = RefactorBot()
    bot.refactor_snippets(
        additional_messages=additional_messages,
        snippets_str=snippets_str,
        file_path=file_path,
        request=request,
        changes_made=changes_made,
    )
