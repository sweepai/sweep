import multiprocessing
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import log

from loguru import logger
from redis import Redis
from tqdm import tqdm

from sweepai.config.server import DEBUG, REDIS_URL
from sweepai.core.entities import Snippet
from sweepai.core.repo_parsing_utils import directory_to_chunks
from sweepai.core.vector_db import get_query_texts_similarity
from sweepai.logn.cache import file_cache
from sweepai.utils.progress import TicketProgress

CACHE_VERSION = "v1.0.14"

if DEBUG:
    redis_client = Redis.from_url(REDIS_URL)
else:
    redis_client = None


def compute_document_tokens(
    content: str,
) -> Counter:  # method that offloads the computation to a separate process
    tokenizer = CodeTokenizer()
    tokens = tokenizer(content)
    return Counter(tokens)


class CustomIndex:
    def __init__(self):
        self.inverted_index = defaultdict(list)
        self.doc_lengths = {}
        self.total_doc_length = 0.0
        self.k1 = 1.2
        self.b = 0.75
        self.metadata = {}  # Store custom metadata here
        self.tokenizer = CodeTokenizer()

    def add_document(
        self, title: str, token_freq: Counter, metadata: dict = {}
    ) -> None:
        doc_id = len(self.doc_lengths)  # increment doc_id
        self.metadata[doc_id] = title  # Store the title as metadata
        doc_length = sum(token_freq.values())
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
        query_tokens = self.tokenizer(query)
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


def tokenize_call(code: str) -> list[str]:
    def check_valid_token(token):
        return token and len(token) > 1

    matches = re.finditer(r"\b\w+\b", code)
    pos = 0
    valid_tokens = []
    for m in matches:
        text = m.group()
        m.start()

        if "_" in text:  # snakecase
            offset = 0
            for part in text.split("_"):
                if check_valid_token(part):
                    valid_tokens.append(part.lower())
                    pos += 1
                offset += len(part) + 1
        elif parts := variable_pattern.findall(text):  # pascal and camelcase
            # first one "MyVariable" second one "myVariable" third one "MYVariable"
            offset = 0
            for part in parts:
                if check_valid_token(part):
                    valid_tokens.append(part.lower())
                    pos += 1
                offset += len(part)
        else:  # everything else
            if check_valid_token(text):
                valid_tokens.append(text.lower())
                pos += 1
    return valid_tokens


def construct_bigrams(tokens: list[str]) -> list[str]:
    res = []
    prev_token = None
    for token in tokens:
        if prev_token:
            joined_token = prev_token + "_" + token
            res.append(joined_token)
        prev_token = token
    return res


def construct_trigrams(tokens: list[str]) -> list[str]:
    res = []
    prev_prev_token = None
    prev_token = None
    for token in tokens:
        if prev_token and prev_prev_token:
            joined_token = prev_prev_token + "_" + prev_token + "_" + token
            res.append(joined_token)
        prev_prev_token = prev_token
        prev_token = token
    return res


class CodeTokenizer:
    def __call__(self, value):
        tokens = tokenize_call(value)
        bigrams = construct_bigrams(tokens)
        trigrams = construct_trigrams(tokens)
        tokens.extend(bigrams)
        tokens.extend(trigrams)
        return tokens


@dataclass
class Document:
    title: str
    content: str


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
    ticket_progress: TicketProgress | None = None,
) -> CustomIndex | None:
    all_docs: list[Document] = snippets_to_docs(snippets, len_repo_cache_dir)
    if len(all_docs) == 0:
        return None
    index = CustomIndex()
    if ticket_progress:
        ticket_progress.search_progress.indexing_total = len(all_docs)
        ticket_progress.save()
    all_tokens = []
    try:
        # use 1/4 the max number of cores
        with multiprocessing.Pool(processes=multiprocessing.cpu_count() // 4) as p:
            for i, document_token_freq in tqdm(
                enumerate(
                    p.imap(compute_document_tokens, [doc.content for doc in all_docs])
                )
            ):
                all_tokens.append(document_token_freq)
                if ticket_progress and i % 200 == 0:
                    ticket_progress.search_progress.indexing_progress = i
                    ticket_progress.save()
        for doc, document_token_freq in tqdm(
            zip(all_docs, all_tokens), desc="Indexing"
        ):
            index.add_document(
                title=doc.title, token_freq=document_token_freq  # snippet.denotation
            )
    except FileNotFoundError as e:
        logger.exception(e)

    return index


@dataclass
class Documentation:
    url: str
    content: str


def prepare_index_from_docs(docs: list[tuple[str, str]]) -> CustomIndex | None:
    """Prepare an index from a list of documents.

    This function takes a list of documents as input and returns an index.
    """
    all_docs = [Documentation(url, content) for url, content in docs]
    if len(all_docs) == 0:
        return None
    # Create the index based on the schema
    index = CustomIndex()
    try:
        for doc in tqdm(all_docs, total=len(all_docs)):
            index.add_document(
                title=f"{doc.url}", token_freq=compute_document_tokens(doc.content)
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
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.exception(e)
        return {}


@file_cache(ignore_params=["snippets"])
def compute_vector_search_scores(query, snippets: list[Snippet]):
    # get get dict of snippet to score
    snippet_str_to_contents = {
        snippet.denotation: snippet.get_snippet(add_ellipsis=False, add_lines=False)
        for snippet in snippets
    }
    snippet_contents_array = list(snippet_str_to_contents.values())
    query_snippet_similarities = get_query_texts_similarity(
        query, snippet_contents_array
    )
    snippet_denotations = [snippet.denotation for snippet in snippets]
    snippet_denotation_to_scores = {
        snippet_denotations[i]: score
        for i, score in enumerate(query_snippet_similarities)
    }
    return snippet_denotation_to_scores


@file_cache(ignore_params=["sweep_config", "ticket_progress"])
def prepare_lexical_search_index(
    repo_directory,
    sweep_config,
    ticket_progress: TicketProgress | None = None,
    ref_name: str | None = None,  # used for caching on different refs
):
    snippets, file_list = directory_to_chunks(repo_directory, sweep_config)
    index = prepare_index_from_snippets(
        snippets,
        len_repo_cache_dir=len(repo_directory) + 1,
        ticket_progress=ticket_progress,
    )
    return file_list, snippets, index


if __name__ == "__main__":
    repo_directory = os.getenv("REPO_DIRECTORY")
    from sweepai.config.client import SweepConfig
    sweep_config = SweepConfig()
    assert repo_directory
    _, _ , index = prepare_lexical_search_index(repo_directory, sweep_config, None, None)
    result = search_index("logger export", index)
    # print some of the keys
    print(list(result.keys())[:5])
    # print the first 2 result keys sorting by value
    print(sorted(result.items(), key=lambda x: result.get(x, 0), reverse=True)[:5])