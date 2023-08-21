import concurrent.futures
import glob
import json
import os
import re
import shutil
import time

import modal
from git.repo import Repo
from github import Github
from loguru import logger
from modal import method
from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from tqdm import tqdm

from sweepai.core.entities import Snippet
from sweepai.core.repo_parsing_utils import repo_to_chunks
from sweepai.utils.event_logger import posthog
from sweepai.utils.hash import hash_sha256
from sweepai.utils.scorer import compute_score, get_factors, get_scores
from sweepai.config.client import SweepConfig
from sweepai.config.server import (
    ENV,
    DB_MODAL_INST_NAME,
    UTILS_MODAL_INST_NAME,
    REDIS_URL,
    BOT_TOKEN_NAME,
)
from ..utils.github_utils import get_token


stub = modal.Stub(DB_MODAL_INST_NAME)
model_volume = modal.NetworkFileSystem.persisted(f"{ENV}-storage")
MODEL_DIR = "/root/cache/model"
DEEPLAKE_DIR = "/root/cache/"
DISKCACHE_DIR = "/root/cache/diskcache/"
DEEPLAKE_FOLDER = "deeplake/"
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


image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install("deeplake==3.6.17", "sentence-transformers")
    .pip_install(
        "openai",
        "PyGithub",
        "loguru",
        "docarray",
        "GitPython",
        "tqdm",
        "anthropic",
        "posthog",
        "redis",
        "pyyaml",
        "rapidfuzz",
        "whoosh",
        "tree-sitter-languages",
    )
    .run_function(download_models)
)
secrets = [
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("github"),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name("posthog"),
    modal.Secret.from_name("redis_url"),
    modal.Secret.from_dict({"TRANSFORMERS_CACHE": MODEL_DIR}),
]


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


@stub.cls(
    image=image,
    secrets=secrets,
    network_file_systems={MODEL_DIR: model_volume},
    keep_warm=1 if ENV == "prod" else 0,
    gpu="T4",
    retries=modal.Retries(max_retries=5, backoff_coefficient=2, initial_delay=5),
    timeout=timeout,
)
class Embedding:
    def __enter__(self):
        from sentence_transformers import (  # pylint: disable=import-error
            SentenceTransformer,
        )

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
        )

    @method()
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


@stub.cls(
    image=image,
    secrets=secrets,
    network_file_systems={MODEL_DIR: model_volume},
    keep_warm=1,
    retries=modal.Retries(max_retries=5, backoff_coefficient=2, initial_delay=5),
    cpu=2,  # this can change later
    timeout=timeout,
)
class CPUEmbedding:
    def __enter__(self):
        from sentence_transformers import (  # pylint: disable=import-error
            SentenceTransformer,
        )

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
        )

    @method()
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
            return CPUEmbedding.compute.call(texts)  # pylint: disable=no-member
        else:
            batches = [
                texts[i : i + ModalEmbeddingFunction.batch_size]
                for i in range(0, len(texts), ModalEmbeddingFunction.batch_size)
            ]
            batches = [batch for batch in batches if len(batch) > 0]
            logger.info([len(batch) for batch in batches])
            results = []
            for batch in tqdm(
                Embedding.compute.map(batches)  # pylint: disable=no-member
            ):
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
            retry = Retry(ExponentialBackoff(), 3)
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

    if cache_inst and cache_success:
        try:
            github_cache_key = f"github-{commit_hash}{CACHE_VERSION}"
            cache_hit = cache_inst.get(github_cache_key)
            if cache_hit:
                deeplake_items = json.loads(cache_hit)
                logger.info(f"Cache hit for {repo_name}")
            else:
                deeplake_items = None
                logger.info(f"Cache miss for {repo_name}")

            if deeplake_items:
                deeplake_vs = init_deeplake_vs(repo_name)
                deeplake_vs.add(
                    text=deeplake_items["ids"],
                    embedding=deeplake_items["embeddings"],
                    metadata=deeplake_items["metadatas"],
                )
                logger.info(f"Returning deeplake vs for {repo_name}")
                return deeplake_vs
            else:
                logger.info(f"Cache for {repo_name} is empty")
        except:
            logger.info(f"Failed to get cache for {repo_name}")
    logger.info(f"Downloading repository and indexing for {repo_name}...")
    start = time.time()
    logger.info("Recursively getting list of files...")

    repo_url = f"https://x-access-token:{token}@github.com/{repo_name}.git"
    shutil.rmtree("repo", ignore_errors=True)

    branch_name = SweepConfig.get_branch(repo)

    git_repo = Repo.clone_from(repo_url, "repo")
    git_repo.git.checkout(branch_name)

    snippets, file_list = repo_to_chunks(sweep_config)
    files_to_scores = {}
    score_factors = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        try:
            score_factors = list(
                executor.map(compute_score, file_list, [git_repo] * len(file_list))
            )
            # compute all scores
            all_scores = get_scores(score_factors)
            files_to_scores = {
                file_path: score for file_path, score in zip(file_list, all_scores)
            }
        except Exception as e:
            logger.error(f"Error occurred during parallel file processing: {e}")
            # Clean up resources if necessary
    logger.info(f"Found {len(file_list)} files in repository {repo_name}")

    # chunks.append(chunk)
    # ids.append(f"{file_path}:{start_line}:{end_line}")
    # metadatas.append(
    #     {
    #         "file_path": file_path,
    #         "start": start_line,
    #         "end": end_line,
    #         "score": score,
    #         **additional_metadata,
    #     }
    # )
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

    shutil.rmtree("repo", ignore_errors=True)
    logger.info(f"Getting list of all files took {time.time() - start}")
    logger.info(f"Received {len(documents)} documents from repository {repo_name}")
    collection_name = parse_collection_name(repo_name)
    return compute_deeplake_vs(
        collection_name,
        documents,
        cache_success,
        cache_inst,
        ids,
        metadatas,
        commit_hash,
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


@stub.function(
    image=image,
    secrets=secrets,
    network_file_systems={DISKCACHE_DIR: model_volume},
    timeout=timeout,
    keep_warm=2,
    cpu=CPU,
)
def update_index(
    repo_name,
    installation_id: int,
    sweep_config: SweepConfig = SweepConfig(),
) -> int:
    get_deeplake_vs_from_repo(
        repo_name, installation_id, branch_name=None, sweep_config=sweep_config
    )
    return 0


@stub.function(
    image=image,
    secrets=secrets,
    network_file_systems={DEEPLAKE_DIR: model_volume},
    timeout=timeout,
    keep_warm=1,
    cpu=CPU,
)
def get_relevant_snippets(
    repo_name: str,
    query: str,
    n_results: int,
    installation_id: int,
    username: str | None = None,
    sweep_config: SweepConfig = SweepConfig(),
):
    logger.info("Getting query embedding...")
    query_embedding = CPUEmbedding.compute.call(query)
    logger.info("Starting search by getting vector store...")
    deeplake_vs = get_deeplake_vs_from_repo(
        repo_name=repo_name, installation_id=installation_id, sweep_config=sweep_config
    )
    logger.info("Searching for relevant snippets...")
    results = {"metadata": [], "text": []}
    for n_result in range(n_results, 0, -1):
        try:
            results = deeplake_vs.search(embedding=query_embedding[0], k=n_result)
            break
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
    vector_scores = results["score"]
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
    ]
