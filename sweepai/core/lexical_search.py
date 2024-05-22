from collections.abc import Iterable
import multiprocessing
import os
import re
from collections import Counter, defaultdict
from math import log
import subprocess

from diskcache import Cache
from loguru import logger
from redis import Redis
from tqdm import tqdm

from sweepai.utils.timer import Timer
from sweepai.config.server import CACHE_DIRECTORY, DEBUG, REDIS_URL
from sweepai.core.entities import Snippet
from sweepai.core.repo_parsing_utils import directory_to_chunks
from sweepai.core.vector_db import multi_get_query_texts_similarity
from sweepai.dataclasses.files import Document
from sweepai.logn.cache import file_cache
from sweepai.utils.progress import TicketProgress
from sweepai.config.client import SweepConfig

token_cache = Cache(f'{CACHE_DIRECTORY}/token_cache') # we instantiate a singleton, diskcache will handle concurrency
lexical_index_cache = Cache(f'{CACHE_DIRECTORY}/lexical_index_cache')
snippets_cache = Cache(f'{CACHE_DIRECTORY}/snippets_cache')
CACHE_VERSION = "v1.0.14"

if DEBUG:
    redis_client = Redis.from_url(REDIS_URL)
else:
    redis_client = None



class CustomIndex:
    def __init__(self):
        self.inverted_index = defaultdict(list)
        self.doc_lengths = {}
        self.total_doc_length = 0.0
        self.k1 = 1.2
        self.b = 0.75
        self.metadata = {}  # Store custom metadata here
        self.tokenizer = tokenize_code

    def add_documents(self, documents: Iterable):
        self.doc_lengths = defaultdict(int)
        self.total_doc_length = 0
        self.inverted_index = defaultdict(list)
        
        for doc_id, (title, token_freq, doc_length) in enumerate(documents):
            self.metadata[doc_id] = title
            self.doc_lengths[doc_id] = doc_length
            self.total_doc_length += doc_length
            for token, freq in token_freq.items():
                self.inverted_index[token].append((doc_id, freq))

    def bm25(self, doc_id: str, term: str, term_freq: int) -> float:
        num_docs = len(self.doc_lengths)
        idf = log(
            ((num_docs - len(self.inverted_index[term])) + 0.5)
            / (len(self.inverted_index[term]) + 0.5)
            + 1.0
        )
        doc_length = self.doc_lengths[doc_id]
        tf = ((self.k1 + 1) * term_freq) / (
            term_freq
            + self.k1
            * (
                1
                - self.b
                + self.b
                * (doc_length / (self.total_doc_length / len(self.doc_lengths)))
            )
        )
        return idf * tf

    def search_index(self, query: str) -> list[tuple[str, float, dict]]:
        query_tokens = tokenize_code(query)
        scores = defaultdict(float)

        for token in query_tokens:
            for doc_id, term_freq in self.inverted_index.get(token, []):
                scores[doc_id] += self.bm25(doc_id, token, term_freq)

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Attach metadata to the results
        results_with_metadata = [
            (self.metadata[doc_id], score, self.metadata.get(doc_id, {}))
            for doc_id, score in sorted_scores
        ]

        return results_with_metadata

variable_pattern = re.compile(r"([A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z]|$))")


def tokenize_code(code: str) -> list[str]:
    matches = re.finditer(r"\b\w{2,}\b", code)
    tokens = []
    for m in matches:
        text = m.group()

        if "_" in text:  # snakecase
            for part in text.split("_"):
                if len(part) > 1:
                    tokens.append(part.lower())
        elif parts := variable_pattern.findall(text):  # pascal and camelcase
            for part in parts:
                if len(part) > 1:
                    tokens.append(part.lower())
        else:
            tokens.append(text.lower())

    bigrams = [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]
    trigrams = [f"{tokens[i]}_{tokens[i + 1]}_{tokens[i + 2]}" for i in range(len(tokens) - 2)]
    tokens.extend(bigrams + trigrams)
    
    return tokens

def compute_document_tokens(
    content: str,
) -> tuple[Counter, int]:  # method that offloads the computation to a separate process
    results = token_cache.get(content)
    if results is not None:
        return results
    tokens = tokenize_code(content)
    result = (Counter(tokens), len(tokens))
    token_cache[content] = result
    return result

def snippets_to_docs(snippets: list[Snippet], len_repo_cache_dir):
    docs = []
    for snippet in snippets:
        docs.append(
            Document(
                title=f"{snippet.file_path[len_repo_cache_dir:]}:{snippet.start}-{snippet.end}",
                content=snippet.get_snippet(add_ellipsis=False, add_lines=False),
            )
        )
    return docs


@file_cache(ignore_params=["ticket_progress", "len_repo_cache_dir"])
def prepare_index_from_snippets(
    snippets: list[Snippet],
    len_repo_cache_dir: int = 0,
    do_not_use_file_cache: bool = False,
) -> CustomIndex | None:
    all_docs: list[Document] = snippets_to_docs(snippets, len_repo_cache_dir)
    if len(all_docs) == 0:
        return None
    index = CustomIndex()
    all_tokens = []
    all_lengths = []
    try:
        with multiprocessing.Pool(processes=multiprocessing.cpu_count() // 2) as p:
            results = p.map(
                compute_document_tokens,
                tqdm(
                    [doc.content for doc in all_docs],
                    total=len(all_docs),
                    desc="Tokenizing documents"
                )
            )
            all_tokens, all_lengths = zip(*results)
        all_titles = [doc.title for doc in all_docs]
        index.add_documents(
            tqdm(zip(all_titles, all_tokens, all_lengths), total=len(all_docs), desc="Indexing")
        )
    except FileNotFoundError as e:
        logger.exception(e)

    return index


def search_index(query, index: CustomIndex):
    """Search the index based on a query.

    This function takes a query and an index as input and returns a dictionary of document IDs
    and their corresponding scores.
    """
    """Title, score, content"""
    if index is None:
        return {}
    try:
        # Create a query parser for the "content" field of the index
        results_with_metadata = index.search_index(query)
        # Search the index
        res = {}
        for doc_id, score, _ in results_with_metadata:
            if doc_id not in res:
                res[doc_id] = score
        # min max normalize scores from 0.5 to 1
        if len(res) == 0:
            max_score = 1
            min_score = 0
        else:
            max_score = max(res.values())
            min_score = min(res.values()) if min(res.values()) < max_score else 0
        res = {k: (v - min_score) / (max_score - min_score) for k, v in res.items()}
        return res
    except Exception as e:
        logger.exception(e)
        return {}

SNIPPET_FORMAT = """File path: {file_path}

{contents}"""

# @file_cache(ignore_params=["snippets"])
def compute_vector_search_scores(queries: list[str], snippets: list[Snippet]):
    # get get dict of snippet to score
    with Timer() as timer:
        snippet_str_to_contents = {
            snippet.denotation: SNIPPET_FORMAT.format(
                file_path=snippet.file_path,
                contents=snippet.get_snippet(add_ellipsis=False, add_lines=False),
            )
            for snippet in snippets
        }
    logger.info(f"Snippet to contents took {timer.time_elapsed:.2f} seconds")
    snippet_contents_array = list(snippet_str_to_contents.values())
    multi_query_snippet_similarities = multi_get_query_texts_similarity(
        queries, snippet_contents_array
    )
    snippet_denotations = [snippet.denotation for snippet in snippets]
    snippet_denotation_to_scores = [{
        snippet_denotations[i]: score
        for i, score in enumerate(query_snippet_similarities)
    } for query_snippet_similarities in multi_query_snippet_similarities]
    return snippet_denotation_to_scores

def get_lexical_cache_key(repo_directory: str, commit_hash: str | None = None):
    commit_hash = commit_hash or subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_directory, capture_output=True, text=True).stdout.strip()
    return f"{repo_directory}_{commit_hash}_{CACHE_VERSION}"

@file_cache(ignore_params=["sweep_config", "ticket_progress"])
def prepare_lexical_search_index(
    repo_directory: str,
    sweep_config: SweepConfig,
    do_not_use_file_cache: bool = False # choose to not cache results
):
    lexical_cache_key = get_lexical_cache_key(repo_directory)

    snippets_results = snippets_cache.get(lexical_cache_key)
    if snippets_results is None:
        snippets, file_list = directory_to_chunks(
            repo_directory, sweep_config, do_not_use_file_cache=do_not_use_file_cache
        )
    else:
        snippets, file_list = snippets_results

    index = lexical_index_cache.get(lexical_cache_key)
    if index is None:
        index = prepare_index_from_snippets(
            snippets,
            len_repo_cache_dir=len(repo_directory) + 1,
            do_not_use_file_cache=do_not_use_file_cache,
        )
        lexical_index_cache[lexical_cache_key] = index

    return file_list, snippets, index


if __name__ == "__main__":
    repo_directory = os.getenv("REPO_DIRECTORY")
    sweep_config = SweepConfig()
    assert repo_directory
    import time
    start = time.time()
    _, _ , index = prepare_lexical_search_index(repo_directory, sweep_config, None)
    result = search_index("logger export", index)
    print("Time taken:", time.time() - start)
    # print some of the keys
    print(list(result.keys())[:5])
    # print the first 2 result keys sorting by value
    print(sorted(result.items(), key=lambda x: result.get(x, 0), reverse=True)[:5])
