import json
import re
import time

from github import Github
from loguru import logger
import numpy as np
from redis import Redis
from redis.backoff import ConstantBackoff
from redis.retry import Retry
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError

from sweepai.core.entities import Snippet
from sweepai.core.lexical_search import prepare_index_from_snippets, search_index
from sweepai.core.repo_parsing_utils import repo_to_chunks
from sweepai.utils.event_logger import posthog
from sweepai.utils.hash import hash_sha256
from sweepai.utils.scorer import compute_score, get_scores
from sweepai.config.client import SweepConfig
from sweepai.config.server import REDIS_URL, SENTENCE_TRANSFORMERS_MODEL
from ..utils.github_utils import ClonedRepo, get_token


MODEL_DIR = "cache/model"
DEEPLAKE_DIR = "cache/"
DISKCACHE_DIR = "cache/diskcache/"
DEEPLAKE_FOLDER = "cache/deeplake/"
BATCH_SIZE = 128
# SENTENCE_TRANSFORMERS_MODEL = "sentence-transformers/all-mpnet-base-v2"
timeout = 60 * 60  # 30 minutes
CACHE_VERSION = "v1.0.11"
MAX_FILES = 500
CPU = 1


def download_models():
    from sentence_transformers import (  # pylint: disable=import-error
        SentenceTransformer,
    )

    model = SentenceTransformer(SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR)


def init_deeplake_vs(repo_name):
    from deeplake.core.vectorstore.deeplake_vectorstore import (
        DeepLakeVectorStore,
    )  # pylint: disable=import-error

    deeplake_repo_path = f"mem://{DEEPLAKE_FOLDER}{repo_name}"
    deeplake_vector_store = DeepLakeVectorStore(path=deeplake_repo_path)
    return deeplake_vector_store


def parse_collection_name(name: str) -> str:
    # Replace any non-alphanumeric characters with hyphens
    name = re.sub(r"[^\w-]", "--", name)
    # Ensure the name is between 3 and 63 characters and starts/ends with alphanumeric
    name = re.sub(r"^(-*\w{0,61}\w)-*$", r"\1", name[:63].ljust(3, "x"))
    return name


class CPUEmbedding:
    def __init__(self):
        from sentence_transformers import (  # pylint: disable=import-error
            SentenceTransformer,
        )

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
        )

    def compute(self, texts: list[str]) -> list[list[float]]:
        logger.info(f"Computing embeddings for {len(texts)} texts")
        vector = self.model.encode(texts, show_progress_bar=True, batch_size=BATCH_SIZE)
        if vector.shape[0] == 1:
            return [vector.tolist()]
        else:
            return vector.tolist()


class ModalEmbeddingFunction:
    batch_size: int = 1024  # can pick a better constant later

    def __init__(self):
        pass

    def __call__(self, texts: list[str], cpu=False):
        if len(texts) == 0:
            return []
        return CPUEmbedding().compute(texts)  # pylint: disable=no-member


embedding_function = ModalEmbeddingFunction()


def get_deeplake_vs_from_repo(
    cloned_repo: ClonedRepo,
    sweep_config: SweepConfig = SweepConfig(),
):
    installation_id = cloned_repo.installation_id
    repo_full_name = cloned_repo.repo_full_name
    token = get_token(installation_id)
    g = Github(token)
    repo = g.get_repo(repo_full_name)
    commits = repo.get_commits()
    commit_hash = commits[0].sha

    cache_success = False
    cache_inst = None

    if REDIS_URL is not None:
        try:
            # todo: initialize once
            retry = Retry(ConstantBackoff(backoff=1), retries=3)
            cache_inst = Redis.from_url(
                REDIS_URL,
                retry=retry,
                retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError],
            )
            logger.info(f"Successfully connected to redis cache")
            cache_success = True
        except:
            cache_success = False
            logger.error(f"Failed to connect to redis cache")
    else:
        logger.warning(f"REDIS_URL is None, skipping cache")
    logger.info(f"Downloading repository and indexing for {repo_full_name}...")
    start = time.time()
    logger.info("Recursively getting list of files...")

    snippets, file_list = repo_to_chunks(cloned_repo.cache_dir, sweep_config)
    logger.info(f"Found {len(snippets)} snippets in repository {repo_full_name}")
    # prepare lexical search
    index = prepare_index_from_snippets(snippets)
    # scoring for vector search
    files_to_scores = {}
    score_factors = []
    for file_path in file_list:
        score_factor = compute_score(
            file_path[len(cloned_repo.cache_dir) + 1 :], cloned_repo.git_repo
        )
        score_factors.append(score_factor)
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
        documents.append(snippet.content)
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
    return (
        compute_deeplake_vs(
            collection_name,
            documents,
            cache_success,
            cache_inst,
            ids,
            metadatas,
            commit_hash,
        ),
        index,
        len(documents),
    )


def compute_deeplake_vs(
    collection_name, documents, cache_success, cache_inst, ids, metadatas, sha
):
    deeplake_vs = init_deeplake_vs(collection_name)
    if len(documents) > 0:
        logger.info("Computing embeddings...")
        # Check cache here for all documents
        embeddings = [None] * len(documents)
        if cache_inst and cache_success:
            cache_keys = [
                hash_sha256(doc) + SENTENCE_TRANSFORMERS_MODEL + CACHE_VERSION
                for doc in documents
            ]
            cache_values = cache_inst.mget(cache_keys)
            for idx, value in enumerate(cache_values):
                if value is not None:
                    embeddings[idx] = json.loads(value)
        logger.info(
            f"Found {len([x for x in embeddings if x is not None])} embeddings in cache"
        )
        indices_to_compute = [idx for idx, x in enumerate(embeddings) if x is None]
        documents_to_compute = [documents[idx] for idx in indices_to_compute]

        logger.info(f"Computing {len(documents_to_compute)} embeddings...")
        computed_embeddings = embedding_function(documents_to_compute)
        print(np.asarray(computed_embeddings).shape)
        logger.info(f"Computed {len(computed_embeddings)} embeddings")

        for idx, embedding in zip(indices_to_compute, computed_embeddings):
            embeddings[idx] = embedding

        logger.info("Adding embeddings to deeplake vector store...")
        deeplake_vs.add(text=ids, embedding=embeddings, metadata=metadatas)
        logger.info("Added embeddings to deeplake vector store")
        if cache_inst and cache_success and len(documents_to_compute) > 0:
            logger.info(f"Updating cache with {len(computed_embeddings)} embeddings")
            cache_keys = [
                hash_sha256(doc) + SENTENCE_TRANSFORMERS_MODEL + CACHE_VERSION
                for doc in documents_to_compute
            ]
            cache_inst.mset(
                {
                    key: json.dumps(value)
                    for key, value in zip(cache_keys, computed_embeddings)
                }
            )
        return deeplake_vs
    else:
        logger.error("No documents found in repository")
        return deeplake_vs


def update_index(
    repo_name,
    installation_id: int,
    sweep_config: SweepConfig = SweepConfig(),
):
    return get_deeplake_vs_from_repo(
        repo_name, installation_id, branch_name=None, sweep_config=sweep_config
    )


def get_relevant_snippets(
    cloned_repo: ClonedRepo,
    query: str,
    n_results: int,
    username: str | None = None,
    sweep_config: SweepConfig = SweepConfig(),
    lexical=True,
):
    repo_name = cloned_repo.repo_full_name
    installation_id = cloned_repo.installation_id
    logger.info("Getting query embedding...")
    query_embedding = CPUEmbedding().compute(query)  # pylint: disable=no-member
    logger.info("Starting search by getting vector store...")
    deeplake_vs, lexical_index, num_docs = get_deeplake_vs_from_repo(
        cloned_repo, sweep_config=sweep_config
    )
    content_to_lexical_score = search_index(query, lexical_index)
    logger.info(f"Searching for relevant snippets... with {num_docs} docs")
    results = {"metadata": [], "text": []}
    try:
        results = deeplake_vs.search(embedding=query_embedding, k=num_docs)
    except Exception as e:
        logger.error(e)
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
                "n_results": n_results,
            },
        )
        return []
    metadatas = results["metadata"]
    code_scores = [metadata["score"] for metadata in metadatas]
    lexical_scores = []
    for metadata in metadatas:
        if metadata["file_path"] in content_to_lexical_score:
            lexical_scores.append(content_to_lexical_score[metadata["file_path"]])
        else:
            lexical_scores.append(0.75)
    vector_scores = results["score"]
    if lexical:
        combined_scores = [
            code_score + vector_score * lexical_score
            for code_score, vector_score, lexical_score in zip(
                code_scores, vector_scores, lexical_scores
            )
        ]
    else:
        combined_scores = [
            code_score + vector_score
            for code_score, vector_score in zip(code_scores, vector_scores)
        ]
    combined_list = list(zip(combined_scores, metadatas))
    sorted_list = sorted(combined_list, key=lambda x: x[0], reverse=True)
    sorted_metadatas = [metadata for _, metadata in sorted_list]
    relevant_paths = [metadata["file_path"] for metadata in sorted_metadatas]
    logger.info("Relevant paths: {}".format(relevant_paths))
    return [
        Snippet(
            content="",
            start=metadata["start"],
            end=metadata["end"],
            file_path=file_path,
        )
        for metadata, file_path in zip(sorted_metadatas, relevant_paths)
    ][: min(num_docs, 25)]
