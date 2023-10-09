import re

from tree_sitter_languages import get_parser

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import RegexMatchableBaseModel, Snippet
from sweepai.logn import logger

system_prompt = """You are a genius engineer tasked with extracting the code and planning the solution to the following GitHub issue.
Decide whether the file_path {file_path} needs to be modified to solve this issue and the proposed solution.

First determine whether changes in file_path are necessary.
Then, if code changes need to be made in file_path, extract the relevant_new_snippets and write the code_change_description.
In code_change_description, mention each relevant_new_snippet and how to modify it.

1. Analyze the code and extract the relevant_new_snippets.
Extract only the relevant_new_snippets that allow us to write code_change_description for file_path.

<code_analysis file_path=\"{file_path}\">
{{thought about potentially relevant snippet and its relevance to the issue}}
...
</code_analysis>

<relevant_new_snippets>
{{relevant snippet from \"{file_path}\" in the format file_path:start_idx-end_idx. Do not delete any relevant entities.}}
...
</relevant_new_snippets>

2. Generate a code_change_description for \"{file_path}\".
When writing the plan for code changes to \"{file_path}\" keep in mind the user will read the metadata and the relevant_new_snippets.

<code_change_description file_path=\"{file_path}\">
{{The changes are constrained to the file_path and code mentioned in file_path.
These are clear and detailed natural language descriptions of modifications to be made in file_path.
The relevant_snippets_in_repo are read-only.}}
</code_change_description>"""

NO_MODS_KWD = "#NONE"

graph_user_prompt = (
    """\
<READONLY>
<issue_metadata>
{issue_metadata}
</issue_metadata>
{previous_snippets}

<all_symbols_and_files>
{all_symbols_and_files}</all_symbols_and_files>
</READONLY>

<file_path=\"{file_path}\" entities=\"{entities}\">
{code}
</file_path>

Provide the relevant_new_snippets and code_change_description to the file_path above.
If there are no relevant_new_snippets or code_change_description, end your message with """
    + NO_MODS_KWD
)


class GraphContextAndPlan(RegexMatchableBaseModel):
    relevant_new_snippet: list[Snippet]
    code_change_description: str | None
    file_path: str
    entities: str = None

    @classmethod
    def from_string(cls, string: str, file_path: str, **kwargs):
        snippets_pattern = r"""<relevant_new_snippets.*?>(\n)?(?P<relevant_new_snippet>.*)</relevant_new_snippets>"""
        plan_pattern = r"""<code_change_description.*?>(\n)?(?P<code_change_description>.*)</code_change_description>"""
        snippets_match = re.search(snippets_pattern, string, re.DOTALL)
        relevant_new_snippet_match = None
        code_change_description = ""
        relevant_new_snippet = []
        if not snippets_match:
            return cls(
                relevant_new_snippet=relevant_new_snippet,
                code_change_description=code_change_description,
                file_path=file_path,
                **kwargs,
            )
        relevant_new_snippet_match = snippets_match.group("relevant_new_snippet")
        for raw_snippet in relevant_new_snippet_match.strip().split("\n"):
            if raw_snippet.strip() == NO_MODS_KWD:
                continue
            if ":" not in raw_snippet:
                continue
            generated_file_path, lines = (
                raw_snippet.split(":")[-2],
                raw_snippet.split(":")[-1],
            )  # solves issue with file_path:snippet:line1-line2
            if not generated_file_path or not lines.strip():
                continue
            generated_file_path, lines = (
                generated_file_path.strip(),
                lines.split()[0].strip(),
            )  # second one accounts for trailing text like "1-10 (message)"
            if generated_file_path != file_path:
                continue
            if "-" not in lines:
                continue
            start, end = lines.split("-", 1)
            start, end = extract_int(start), extract_int(end)
            if start is None or end is None:
                continue
            start = int(start)
            end = int(end) - 1
            end = min(end, start + 200)
            if end - start < 20:  # don't allow small snippets
                start = start - 10
                end = start + 10
            snippet = Snippet(file_path=file_path, start=start, end=end, content="")
            relevant_new_snippet.append(snippet)
        plan_match = re.search(plan_pattern, string, re.DOTALL)
        if plan_match:
            code_change_description = plan_match.group(
                "code_change_description"
            ).strip()
            if code_change_description.endswith(NO_MODS_KWD):
                logger.warning(
                    "NO_MODS_KWD found in code_change_description for " + file_path
                )
                code_change_description = None
        return cls(
            relevant_new_snippet=relevant_new_snippet,
            code_change_description=code_change_description,
            file_path=file_path,
            **kwargs,
        )

    def __str__(self) -> str:
        return f"{self.relevant_new_snippet}\n{self.code_change_description}"


class GraphChildBot(ChatGPT):
    def code_plan_extraction(
        self,
        code,
        file_path,
        entities,
        issue_metadata,
        previous_snippets,
        all_symbols_and_files,
    ) -> GraphContextAndPlan:
        python_snippet = extract_python_span(code, entities)
        python_snippet.file_path = file_path
        return GraphContextAndPlan(
            relevant_new_snippet=[python_snippet],
            code_change_description="",
            file_path=file_path,
        )


def extract_int(s):
    match = re.search(r"\d+", s)
    if match:
        return int(match.group())
    return None


def extract_python_span(code: str, entities: str):
    lines = code.split("\n")

    # Identify lines where entities are declared as variables
    variables_with_entity = set()
    lines_with_entity = set()
    for i, line in enumerate(lines):
        for entity in entities:
            if (
                entity in line
                and "=" in line
                and not line.lstrip().startswith(("class ", "def "))
            ):
                variable_name = line.split("=")[0].strip()
                if not variable_name.rstrip().endswith(")"):
                    variables_with_entity.add(variable_name)
                    lines_with_entity.add(i)

    captured_lines = set()

    # Up to the first variable definition
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("class ", "def ")):
            print(line)
            break
    captured_lines.update(range(i))

    parser = get_parser("python")
    tree = parser.parse(code.encode("utf-8"))

    def walk_tree(node):
        if node.type in ["class_definition", "function_definition"]:
            # Check if the entity is in the first line (class Entity or class Class(Entity), etc)
            start_line, end_line = node.start_point[0], node.end_point[0]
            if (
                any(start_line <= line_no <= end_line for line_no in lines_with_entity)
                and node.type == "function_definition"
                and end_line - start_line < 100
            ):
                captured_lines.update(range(start_line, end_line + 1))
            if any(
                entity in node.text.decode("utf-8").split("\n")[0]
                for entity in entities
            ):
                captured_lines.update(range(start_line, end_line + 1))
        for child in node.children:
            walk_tree(child)

    try:
        walk_tree(tree.root_node)
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(e)
        logger.error("Failed to parse python file. Using for loop instead.")
        # Haven't tested this section

        # Capture entire subscope for class and function definitions
        for i, line in enumerate(lines):
            if any(
                entity in line and line.lstrip().startswith(keyword)
                for entity in entities
                for keyword in ["class ", "def "]
            ):
                indent_level = len(line) - len(line.lstrip())
                captured_lines.add(i)

                # Add subsequent lines until a line with a lower indent level is encountered
                j = i + 1
                while j < len(lines):
                    current_indent = len(lines[j]) - len(lines[j].lstrip())
                    if current_indent > indent_level and len(lines[j].lstrip()) > 0:
                        captured_lines.add(j)
                        j += 1
                    else:
                        break
            # For non-variable lines with the entity, capture ±20 lines
            elif any(entity in line for entity in entities):
                captured_lines.update(range(max(0, i - 20), min(len(lines), i + 21)))

    captured_lines_list = sorted(list(captured_lines))
    result = []

    # Coalesce lines that are close together
    coalesce = 5
    for i in captured_lines_list:
        if i + coalesce in captured_lines_list and any(
            i + j not in captured_lines for j in range(1, coalesce)
        ):
            captured_lines.update(range(i, i + coalesce))

    captured_lines_list = sorted(list(captured_lines))

    previous_line_number = -1  # Initialized to an impossible value

    # Construct the result with line numbers and mentions
    for i in captured_lines_list:
        line = lines[i]

        if previous_line_number != -1 and i - previous_line_number > 1:
            result.append("...\n")

        result.append(line)

        previous_line_number = i

    return Snippet(file_path="", start=0, end=0, content="\n".join(result))


if __name__ == "__main__":
    file = r'''
import json
import re
import time
from functools import lru_cache
from typing import Generator, List

import numpy as np
import replicate
import requests
import traceback
from deeplake.core.vectorstore.deeplake_vectorstore import (  # pylint: disable=import-error
    VectorStore,
)
from redis import Redis
from sentence_transformers import SentenceTransformer  # pylint: disable=import-error
from tqdm import tqdm

from sweepai.logn import file_cache, logger
from sweepai.config.client import SweepConfig
from sweepai.config.server import (
    BATCH_SIZE,
    HUGGINGFACE_TOKEN,
    HUGGINGFACE_URL,
    REDIS_URL,
    REPLICATE_API_KEY,
    REPLICATE_URL,
    SENTENCE_TRANSFORMERS_MODEL,
    VECTOR_EMBEDDING_SOURCE,
)
from sweepai.core.entities import Snippet
from sweepai.core.lexical_search import prepare_index_from_snippets, search_index
from sweepai.core.repo_parsing_utils import repo_to_chunks
from sweepai.utils.event_logger import posthog
from sweepai.utils.hash import hash_sha256
from sweepai.utils.scorer import compute_score, get_scores

from ..utils.github_utils import ClonedRepo

MODEL_DIR = "/tmp/cache/model"
DEEPLAKE_DIR = "/tmp/cache/"
timeout = 60 * 60  # 30 minutes
CACHE_VERSION = "v1.0.13"
MAX_FILES = 500

redis_client = Redis.from_url(REDIS_URL)


def download_models():
    from sentence_transformers import (  # pylint: disable=import-error
        SentenceTransformer,
    )

    model = SentenceTransformer(SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR)


def init_deeplake_vs(repo_name):
    deeplake_repo_path = f"mem://{int(time.time())}{repo_name}"
    deeplake_vector_store = VectorStore(
        path=deeplake_repo_path, read_only=False, overwrite=False
    )
    return deeplake_vector_store


def parse_collection_name(name: str) -> str:
    # Replace any non-alphanumeric characters with hyphens
    name = re.sub(r"[^\w-]", "--", name)
    # Ensure the name is between 3 and 63 characters and starts/ends with alphanumeric
    name = re.sub(r"^(-*\w{0,61}\w)-*$", r"\1", name[:63].ljust(3, "x"))
    return name


def embed_huggingface(texts):
    """Embeds a list of texts using Hugging Face's API."""
    for i in range(3):
        try:
            headers = {
                "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
                "Content-Type": "application/json",
            }
            response = requests.post(
                HUGGINGFACE_URL, headers=headers, json={"inputs": texts}
            )
            return response.json()["embeddings"]
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Error occurred when sending request to Hugging Face endpoint: {traceback.format_exc()}"
            )


def embed_replicate(texts):
    client = replicate.Client(api_token=REPLICATE_API_KEY)
    for i in range(3):
        try:
            outputs = client.run(REPLICATE_URL, input={"text_batch": json.dumps(texts)}, timeout=60)
        except Exception as e:
            logger.error(f"Replicate timeout: {traceback.format_exc()}")
    return [output["embedding"] for output in outputs]


@lru_cache(maxsize=64)
def embed_texts(texts: tuple[str]):
    logger.info(
        f"Computing embeddings for {len(texts)} texts using {VECTOR_EMBEDDING_SOURCE}..."
    )
    match VECTOR_EMBEDDING_SOURCE:
        case "sentence-transformers":
            sentence_transformer_model = SentenceTransformer(
                SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
            )
            vector = sentence_transformer_model.encode(
                texts, show_progress_bar=True, batch_size=BATCH_SIZE
            )
            return vector
        case "openai":
            import openai

            embeddings = []
            for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE), disable=False):
                try:
                    response = openai.Embedding.create(
                        input=batch, model="text-embedding-ada-002"
                    )
                    embeddings.extend([r["embedding"] for r in response["data"]])
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    logger.error(traceback.format_exc())
                    logger.error(f"Failed to get embeddings for {batch}")
            return embeddings
        case "huggingface":
            if HUGGINGFACE_URL and HUGGINGFACE_TOKEN:
                embeddings = []
                for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE), disable=False):
                    embeddings.extend(embed_huggingface(texts))
                return embeddings
            else:
                raise Exception("Hugging Face URL and token not set")
        case "replicate":
            if REPLICATE_API_KEY:
                embeddings = []
                for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE)):
                    embeddings.extend(embed_replicate(batch))
                return embeddings
            else:
                raise Exception("Replicate URL and token not set")
        case _:
            raise Exception("Invalid vector embedding mode")
    logger.info(
        f"Computed embeddings for {len(texts)} texts using {VECTOR_EMBEDDING_SOURCE}"
    )


def embedding_function(texts: list[str]):
    # For LRU cache to work
    return embed_texts(tuple(texts))


def get_deeplake_vs_from_repo(
    cloned_repo: ClonedRepo,
    sweep_config: SweepConfig = SweepConfig(),
):
    deeplake_vs = None

    repo_full_name = cloned_repo.repo_full_name
    repo = cloned_repo.repo
    commits = repo.get_commits()
    commit_hash = commits[0].sha

    logger.info(f"Downloading repository and indexing for {repo_full_name}...")
    start = time.time()
    logger.info("Recursively getting list of files...")
    snippets, file_list = repo_to_chunks(cloned_repo.cache_dir, sweep_config)
    logger.info(f"Found {len(snippets)} snippets in repository {repo_full_name}")
    # prepare lexical search
    index = prepare_index_from_snippets(
        snippets, len_repo_cache_dir=len(cloned_repo.cache_dir) + 1
    )
    logger.print("Prepared index from snippets")
    # scoring for vector search
    files_to_scores = {}
    score_factors = []
    for file_path in tqdm(file_list):
        if not redis_client:
            score_factor = compute_score(
                file_path[len(cloned_repo.cache_dir) + 1 :], cloned_repo.git_repo
            )
            score_factors.append(score_factor)
            continue
        cache_key = hash_sha256(file_path) + CACHE_VERSION
        try:
            cache_value = redis_client.get(cache_key)
        except Exception as e:
            logger.error(traceback.format_exc())
            cache_value = None
        if cache_value is not None:
            score_factor = json.loads(cache_value)
            score_factors.append(score_factor)
        else:
            score_factor = compute_score(
                file_path[len(cloned_repo.cache_dir) + 1 :], cloned_repo.git_repo
            )
            score_factors.append(score_factor)
            redis_client.set(cache_key, json.dumps(score_factor))
    # compute all scores
    all_scores = get_scores(score_factors)
    files_to_scores = {
        file_path: score for file_path, score in zip(file_list, all_scores)
    }
    logger.info(f"Found {len(file_list)} files in repository {repo_full_name}")

    documents = []
    metadatas = []
    ids = []
    for snippet in snippets:
        documents.append(snippet.get_snippet(add_ellipsis=False, add_lines=False))
        metadata = {
            "file_path": snippet.file_path[len(cloned_repo.cache_dir) + 1 :],
            "start": snippet.start,
            "end": snippet.end,
            "score": files_to_scores[snippet.file_path],
        }
        metadatas.append(metadata)
        gh_file_path = snippet.file_path[len("repo/") :]
        ids.append(f"{gh_file_path}:{snippet.start}:{snippet.end}")
    logger.info(f"Getting list of all files took {time.time() - start}")
    logger.info(f"Received {len(documents)} documents from repository {repo_full_name}")
    collection_name = parse_collection_name(repo_full_name)

    deeplake_vs = deeplake_vs or compute_deeplake_vs(
        collection_name, documents, ids, metadatas, commit_hash
    )

    return deeplake_vs, index, len(documents)


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
            logger.print([len(embedding) for embedding in embeddings])
            logger.error(
                "Failed to convert embeddings to numpy array, recomputing all of them"
            )
            embeddings = embedding_function(documents)
            embeddings = np.array(embeddings, dtype=np.float32)

        logger.info("Adding embeddings to deeplake vector store...")
        deeplake_vs = init_deeplake_vs(collection_name)
        deeplake_vs.add(text=ids, embedding=embeddings, metadata=metadatas)
        logger.info("Added embeddings to deeplake vector store")
        if redis_client and len(documents_to_compute) > 0:
            logger.info(f"Updating cache with {len(computed_embeddings)} embeddings")
            cache_keys = [
                hash_sha256(doc)
                + SENTENCE_TRANSFORMERS_MODEL
                + VECTOR_EMBEDDING_SOURCE
                + CACHE_VERSION
                for doc in documents_to_compute
            ]
            redis_client.mset(
                {
                    key: json.dumps(
                        embedding.tolist()
                        if isinstance(embedding, np.ndarray)
                        else embedding
                    )
                    for key, embedding in zip(cache_keys, computed_embeddings)
                }
            )
        return deeplake_vs
    else:
        logger.error("No documents found in repository")
        return deeplake_vs


# Only works on functions without side effects
@file_cache(ignore_params=["cloned_repo", "sweep_config", "token"])
def get_relevant_snippets(
    cloned_repo: ClonedRepo,
    query: str,
    username: str | None = None,
    sweep_config: SweepConfig = SweepConfig(),
    lexical=True,
):
    repo_name = cloned_repo.repo_full_name
    installation_id = cloned_repo.installation_id
    logger.info("Getting query embedding...")
    query_embedding = embedding_function([query])  # pylint: disable=no-member
    logger.info("Starting search by getting vector store...")
    deeplake_vs, lexical_index, num_docs = get_deeplake_vs_from_repo(
        cloned_repo, sweep_config=sweep_config
    )
    content_to_lexical_score = search_index(query, lexical_index)
    logger.info(f"Found {len(content_to_lexical_score)} lexical results")
    logger.info(f"Searching for relevant snippets... with {num_docs} docs")
    results = {"metadata": [], "text": []}
    try:
        results = deeplake_vs.search(embedding=query_embedding, k=num_docs)
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(traceback.format_exc())
    logger.info("Fetched relevant snippets...")
    if len(results["text"]) == 0:
        logger.info(f"Results query {query} was empty")
        logger.info(f"Results: {results}")
        if username is None:
            username = "anonymous"
        posthog.capture(
            username,
            "failed",
            {
                "reason": "Results query was empty",
                "repo_name": repo_name,
                "installation_id": installation_id,
                "query": query,
            },
        )
        return []
    metadatas = results["metadata"]
    code_scores = [metadata["score"] for metadata in metadatas]
    lexical_scores = []
    for metadata in metadatas:
        key = f"{metadata['file_path']}:{str(metadata['start'])}:{str(metadata['end'])}"
        if key in content_to_lexical_score:
            lexical_scores.append(content_to_lexical_score[key])
        else:
            lexical_scores.append(0.3)
    vector_scores = results["score"]
    combined_scores = [
        code_score * 4
        + vector_score
        + lexical_score * 2.5  # increase weight of lexical search
        for code_score, vector_score, lexical_score in zip(
            code_scores, vector_scores, lexical_scores
        )
    ]
    combined_list = list(zip(combined_scores, metadatas))
    sorted_list = sorted(combined_list, key=lambda x: x[0], reverse=True)
    sorted_metadatas = [metadata for _, metadata in sorted_list]
    relevant_paths = [metadata["file_path"] for metadata in sorted_metadatas]
    logger.info("Relevant paths: {}".format(relevant_paths[:5]))
    return [
        Snippet(
            content="",
            start=metadata["start"],
            end=metadata["end"],
            file_path=file_path,
        )
        for metadata, file_path in zip(sorted_metadatas, relevant_paths)
    ][:num_docs]


def chunk(texts: List[str], batch_size: int) -> Generator[List[str], None, None]:
    """
    Split a list of texts into batches of a given size for embed_texts.

    Args:
    ----
        texts (List[str]): A list of texts to be chunked into batches.
        batch_size (int): The maximum number of texts in each batch.

    Yields:
    ------
        Generator[List[str], None, None]: A generator that yields batches of texts as lists.

    Example:
    -------
        texts = ["text1", "text2", "text3", "text4", "text5"]
        batch_size = 2
        for batch in chunk(texts, batch_size):
            print(batch)
        # Output:
        # ['text1', 'text2']
        # ['text3', 'text4']
        # ['text5']
    """
    texts = [text[:4096] if text else " " for text in texts]
    for text in texts:
        assert isinstance(text, str), f"Expected str, got {type(text)}"
        assert len(text) <= 4096, f"Expected text length <= 4096, got {len(text)}"
    for i in range(0, len(texts), batch_size):
        yield texts[i : i + batch_size] if i + batch_size < len(texts) else texts[i:]
'''

    print(extract_int("10, 10-11 (message)"))
    print("\nExtracting Span:")
    span = extract_python_span(file, ["embed_replicate"]).content
    print(span)
    quit()

    # test response for plan
    response = """<code_analysis>
The issue requires moving the is_python_issue bool in sweep_bot to the on_ticket.py flow. The is_python_issue bool is used in the get_files_to_change function in sweep_bot.py to determine if the issue is related to a Python file. This information is then logged and used to generate a plan for the relevant snippets.

In the on_ticket.py file, the get_files_to_change function is called, but the is_python_issue bool is not currently used or logged. The issue also requires using the metadata in on_ticket to log this event to posthog, which is a platform for product analytics.

The posthog.capture function is used in on_ticket.py to log events with specific properties. The properties include various metadata about the issue and the user. The issue requires passing the is_python_issue bool to get_files_to_change and then logging this as an event to posthog.
</code_analysis>

<relevant_new_snippet>
sweepai/handlers/on_ticket.py:590-618
</relevant_new_snippet>

<code_change_description file_path="sweepai/handlers/on_ticket.py">
First, you need to modify the get_files_to_change function call in on_ticket.py to pass the is_python_issue bool. You can do this by adding an argument to the function call at line 690. The argument should be a key-value pair where the key is 'is_python_issue' and the value is the is_python_issue bool.

Next, you need to log the is_python_issue bool as an event to posthog. You can do this by adding a new posthog.capture function call after the get_files_to_change function call. The first argument to posthog.capture should be 'username', the second argument should be a string describing the event (for example, 'is_python_issue'), and the third argument should be a dictionary with the properties to log. The properties should include 'is_python_issue' and its value.

Here is an example of how to make these changes:

```python
# Add is_python_issue to get_files_to_change function call
file_change_requests, plan = sweep_bot.get_files_to_change(is_python_issue=is_python_issue)

# Log is_python_issue to posthog
posthog.capture(username, 'is_python_issue', properties={'is_python_issue': is_python_issue})
```
Please replace 'is_python_issue' with the actual value of the bool.
</code_change_description>"""
    gc_and_plan = GraphContextAndPlan.from_string(
        response, "sweepai/handlers/on_ticket.py"
    )
    # print(gc_and_plan.code_change_description)
