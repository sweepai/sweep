import json
import os
import re
import shutil
import time

from git.repo import Repo
from github import Github
from loguru import logger
from redis import Redis
from redis.backoff import ConstantBackoff
from redis.retry import Retry
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from tqdm import tqdm

from sweepai.core.entities import Snippet
from sweepai.core.lexical_search import prepare_index_from_snippets, search_index
from sweepai.core.repo_parsing_utils import repo_to_chunks
from sweepai.utils.event_logger import posthog
from sweepai.utils.hash import hash_sha256
from sweepai.utils.scorer import compute_score, get_scores
from sweepai.config.client import SweepConfig
from sweepai.config.server import REDIS_URL
from ..utils.github_utils import get_token


MODEL_DIR = "cache/model"
DEEPLAKE_DIR = "cache/"
DISKCACHE_DIR = "cache/diskcache/"
DEEPLAKE_FOLDER = "cache/deeplake/"
BATCH_SIZE = 128
SENTENCE_TRANSFORMERS_MODEL = "sentence-transformers/all-mpnet-base-v2"
timeout = 60 * 60  # 30 minutes
CACHE_VERSION = "v1.0.11"
MAX_FILES = 500
CPU = 1


def download_models():
    from sentence_transformers import (  # pylint: disable=import-error
        SentenceTransformer,
    )

    model = SentenceTransformer(SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR)


# image = (
#     modal.Image.debian_slim()
#     .apt_install("git")
#     .pip_install("deeplake==3.6.17", "sentence-transformers")
#     .pip_install(
#         "openai",
#         "PyGithub",
#         "loguru",
#         "docarray",
#         "GitPython",
#         "tqdm",
#         "anthropic",
#         "posthog",
#         "redis",
#         "pyyaml",
#         "rapidfuzz",
#         "whoosh",
#         "tree-sitter-languages",
#     )
#     .run_function(download_models)
# )
# secrets = [
#     modal.Secret.from_name(BOT_TOKEN_NAME),
#     modal.Secret.from_name("github"),
#     modal.Secret.from_name("openai-secret"),
#     modal.Secret.from_name("posthog"),
#     modal.Secret.from_name("redis_url"),
#     modal.Secret.from_dict({"TRANSFORMERS_CACHE": MODEL_DIR}),
# ]


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


class Embedding:
    def __init__(self):
        from sentence_transformers import (  # pylint: disable=import-error
            SentenceTransformer,
        )

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
        )

    def compute(self, texts: list[str]):
        logger.info(f"Computing embeddings for {len(texts)} texts")
        vector = self.model.encode(
            texts, show_progress_bar=True, batch_size=BATCH_SIZE
        ).tolist()
        try:
            logger.info(f"{len(vector)}\n{len(vector[0])}")
        except Exception as e:
            print(f"oops {e}")
            pass
        return vector


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
        vector = self.model.encode(
            texts, show_progress_bar=True, batch_size=BATCH_SIZE
        ).tolist()
        try:
            logger.info(f"{len(vector)}\n{len(vector[0])}")
        except Exception as e:
            logger.info(f"oops {e}")
            pass
        return vector


class ModalEmbeddingFunction:
    batch_size: int = 4096  # can pick a better constant later

    def __init__(self):
        pass

    def __call__(self, texts: list[str], cpu=False):
        if len(texts) == 0:
            return []
        if cpu or len(texts) < 10:
            return CPUEmbedding().compute(texts)  # pylint: disable=no-member
        else:
            batches = [
                texts[i : i + ModalEmbeddingFunction.batch_size]
                for i in range(0, len(texts), ModalEmbeddingFunction.batch_size)
            ]
            batches = [batch for batch in batches if len(batch) > 0]
            logger.info([len(batch) for batch in batches])
            results = []
            for batch in tqdm(
                Embedding().compute(batches)
            ):  # pylint: disable=no-member
                results.extend(batch)

            return results


embedding_function = ModalEmbeddingFunction()


def get_deeplake_vs_from_repo(
    repo_name: str,
    installation_id: int,
    branch_name: str | None = None,
    sweep_config: SweepConfig = SweepConfig(),
):
    token = get_token(installation_id)
    g = Github(token)
    repo = g.get_repo(repo_name)
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
    logger.info(f"Downloading repository and indexing for {repo_name}...")
    start = time.time()
    logger.info("Recursively getting list of files...")

    repo_url = f"https://x-access-token:{token}@github.com/{repo_name}.git"
    shutil.rmtree("repo", ignore_errors=True)

    branch_name = SweepConfig.get_branch(repo)
    if os.path.exists("repo"):
        shutil.rmtree("repo", ignore_errors=True)
    git_repo = Repo.clone_from(repo_url, "repo")
    git_repo.git.checkout(branch_name)

    snippets, file_list = repo_to_chunks(sweep_config)
    # prepare lexical search
    index = prepare_index_from_snippets(snippets)
    # scoring for vector search
    files_to_scores = {}
    score_factors = []
    for file_path in file_list:
        score_factor = compute_score(file_path, git_repo)
        score_factors.append(score_factor)
    # compute all scores
    all_scores = get_scores(score_factors)
    files_to_scores = {
        file_path: score for file_path, score in zip(file_list, all_scores)
    }
    logger.info(f"Found {len(file_list)} files in repository {repo_name}")

    documents = []
    metadatas = []
    ids = []
    for snippet in snippets:
        documents.append(snippet.content)
        metadata = {
            "file_path": snippet.file_path[len("repo/") :],
            "start": snippet.start,
            "end": snippet.end,
            "score": files_to_scores[snippet.file_path],
        }
        metadatas.append(metadata)
        gh_file_path = snippet.file_path[len("repo/") :]
        ids.append(f"{gh_file_path}:{snippet.start}:{snippet.end}")
    logger.info(f"Getting list of all files took {time.time() - start}")
    logger.info(f"Received {len(documents)} documents from repository {repo_name}")
    collection_name = parse_collection_name(repo_name)
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
        logger.info(f"Computed {len(computed_embeddings)} embeddings")

        for idx, embedding in zip(indices_to_compute, computed_embeddings):
            embeddings[idx] = embedding

        logger.info("Adding embeddings to deeplake vector store...")
        deeplake_vs.add(text=ids, embedding=embeddings, metadata=metadatas)
        logger.info("Added embeddings to deeplake vector store")
        if cache_inst and cache_success and len(documents) < 500:
            cache_inst.set(
                f"github-{sha}{CACHE_VERSION}",
                json.dumps(
                    {"metadatas": metadatas, "ids": ids, "embeddings": embeddings}
                ),
            )
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
) -> int:
    get_deeplake_vs_from_repo(
        repo_name, installation_id, branch_name=None, sweep_config=sweep_config
    )
    return 0


def get_relevant_snippets(
    repo_name: str,
    query: str,
    n_results: int,
    installation_id: int,
    username: str | None = None,
    sweep_config: SweepConfig = SweepConfig(),
    lexical=True,
):
    logger.info("Getting query embedding...")
    query_embedding = CPUEmbedding().compute(query)  # pylint: disable=no-member
    logger.info("Starting search by getting vector store...")
    deeplake_vs, lexical_index, num_docs = get_deeplake_vs_from_repo(
        repo_name=repo_name, installation_id=installation_id, sweep_config=sweep_config
    )
    content_to_lexical_score = search_index(query, lexical_index)
    logger.info(f"content_to_lexical_score: {content_to_lexical_score}")
    logger.info("Searching for relevant snippets...")
    results = {"metadata": [], "text": []}
    try:
        results = deeplake_vs.search(embedding=query_embedding, k=num_docs)
    except Exception:
        pass
    logger.info("Fetched relevant snippets...")
    if len(results["text"]) == 0:
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
    # Sort by combined scores
    # Combine the three lists into a single list of tuples
    combined_list = list(zip(combined_scores, metadatas))

    # Sort the combined list based on the combined scores
    sorted_list = sorted(combined_list, key=lambda x: x[0], reverse=True)

    # Extract the sorted metadatas and relevant_paths
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
