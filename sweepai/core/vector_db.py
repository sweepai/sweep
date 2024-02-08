import json
import re
import time
from functools import lru_cache
from typing import Generator, List

import numpy as np
import replicate
import requests

# pylint: disable=import-error
from deeplake.core.vectorstore.deeplake_vectorstore import VectorStore
from loguru import logger
from redis import Redis
from tqdm import tqdm

from sweepai.config.client import SweepConfig, get_blocked_dirs
from sweepai.config.server import (
    BATCH_SIZE,
    HUGGINGFACE_TOKEN,
    HUGGINGFACE_URL,
    REDIS_URL,
    REPLICATE_API_KEY,
    REPLICATE_DEPLOYMENT_URL,
    SENTENCE_TRANSFORMERS_MODEL,
    VECTOR_EMBEDDING_SOURCE,
)
from sweepai.core.lexical_search import prepare_index_from_snippets
from sweepai.core.repo_parsing_utils import repo_to_chunks
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.hash import hash_sha256
from sweepai.utils.progress import TicketProgress
from sweepai.utils.scorer import compute_score, get_scores

MODEL_DIR = "/tmp/cache/model"
DEEPLAKE_DIR = "/tmp/cache/"
timeout = 60 * 60  # 30 minutes
CACHE_VERSION = "v1.0.14"
MAX_FILES = 500

redis_client = Redis.from_url(REDIS_URL)


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
            logger.exception(
                f"Error occurred when sending request to Hugging Face endpoint: {e}"
            )


def embed_replicate(texts: List[str], timeout=180) -> List[np.ndarray]:
    client = replicate.Client(api_token=REPLICATE_API_KEY)
    deployment = client.deployments.get(REPLICATE_DEPLOYMENT_URL)
    e = None
    for i in range(3):
        try:
            prediction = deployment.predictions.create(
                input={"text_batch": json.dumps(texts)}, timeout=timeout
            )
            prediction.wait()
            outputs = prediction.output
            break
        except Exception:
            logger.exception(f"Replicate timeout: {e}")
    else:
        raise Exception(f"Replicate timeout")
    return [output["embedding"] for output in outputs]


@lru_cache(maxsize=64)
def embed_texts(texts: tuple[str]):
    logger.info(
        f"Computing embeddings for {len(texts)} texts using {VECTOR_EMBEDDING_SOURCE}..."
    )
    match VECTOR_EMBEDDING_SOURCE:
        case "openai":
            from openai import OpenAI

            client = OpenAI()

            embeddings = []
            for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE), disable=False):
                try:
                    response = client.embeddings.create(
                        input=batch, model="text-embedding-ada-002"
                    )
                    embeddings.extend([r["embedding"] for r in response["data"]])
                except SystemExit:
                    raise SystemExit
                except Exception:
                    logger.exception("Failed to get embeddings for batch")
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
        case "none":
            return [[0.5]] * len(texts)
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
    blocked_dirs = get_blocked_dirs(repo)
    sweep_config.exclude_dirs.extend(blocked_dirs)
    file_list, snippets, index = prepare_lexical_search_index(
        cloned_repo, sweep_config, repo_full_name, TicketProgress(tracking_id="none")
    )
    # scoring for vector search
    files_to_scores = compute_vector_search_scores(file_list, cloned_repo)

    collection_name, documents, ids, metadatas = prepare_documents_metadata_ids(
        snippets, cloned_repo, files_to_scores, start, repo_full_name
    )

    deeplake_vs = deeplake_vs or compute_deeplake_vs(
        collection_name, documents, ids, metadatas, commit_hash
    )

    return deeplake_vs, index, len(documents)


def prepare_documents_metadata_ids(
    snippets, cloned_repo, files_to_scores, start, repo_full_name
):
    documents = []
    metadatas = []
    ids = []
    for snippet in snippets:
        documents.append(snippet.get_snippet(add_ellipsis=False, add_lines=False))
        metadata = {
            "file_path": snippet.file_path[len(cloned_repo.cached_dir) + 1 :],
            "start": snippet.start,
            "end": snippet.end,
            "score": files_to_scores[snippet.file_path],
        }
        metadatas.append(metadata)
        gh_file_path = snippet.file_path[len("repo") :]
        ids.append(f"{gh_file_path}:{snippet.start}:{snippet.end}")
    logger.info(f"Getting list of all files took {time.time() - start}")
    logger.info(f"Received {len(documents)} documents from repository {repo_full_name}")
    collection_name = parse_collection_name(repo_full_name)
    return collection_name, documents, ids, metadatas


def compute_vector_search_scores(file_list, cloned_repo):
    files_to_scores = {}
    score_factors = []
    for file_path in tqdm(file_list):
        if not redis_client:
            score_factor = compute_score(
                file_path[len(cloned_repo.cached_dir) + 1 :], cloned_repo.git_repo
            )
            score_factors.append(score_factor)
            continue
        cache_key = hash_sha256(file_path) + CACHE_VERSION
        try:
            cache_value = redis_client.get(cache_key)
        except Exception as e:
            logger.exception(e)
            cache_value = None
        if cache_value is not None:
            score_factor = json.loads(cache_value)
            score_factors.append(score_factor)
        else:
            score_factor = compute_score(
                file_path[len(cloned_repo.cached_dir) + 1 :], cloned_repo.git_repo
            )
            score_factors.append(score_factor)
            redis_client.set(cache_key, json.dumps(score_factor))
    # compute all scores
    all_scores = get_scores(score_factors)
    files_to_scores = {
        file_path[len(cloned_repo.cached_dir) + 1 :]: score
        for file_path, score in zip(file_list, all_scores)
    }
    return files_to_scores


def prepare_lexical_search_index(
    cloned_repo,
    sweep_config,
    repo_full_name,
    ticket_progress: TicketProgress | None = None,
):
    snippets, file_list = repo_to_chunks(cloned_repo.cached_dir, sweep_config)
    logger.info(f"Found {len(snippets)} snippets in repository {repo_full_name}")
    # prepare lexical search
    index = prepare_index_from_snippets(
        snippets,
        len_repo_cache_dir=len(cloned_repo.cached_dir) + 1,
        ticket_progress=ticket_progress,
    )
    return file_list, snippets, index


def compute_deeplake_vs(collection_name, documents, ids, metadatas, sha):
    if len(documents) > 0:
        logger.info(f"Computing embeddings with {VECTOR_EMBEDDING_SOURCE}...")
        # Check cache here for all documents
        embeddings = [None] * len(documents)
        # if len(documents) > 10000:
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

        embeddings = convert_to_numpy_array(embeddings, documents)

        deeplake_vs = init_deeplake_vs(collection_name)
        deeplake_vs.add(text=ids, embedding=embeddings, metadata=metadatas)
        logger.info("Added embeddings to cache")
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


def convert_to_numpy_array(embeddings, documents):
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
    return embeddings


def compute_embeddings(documents):
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

        embeddings = convert_to_numpy_array(embeddings, documents)
    return embeddings, documents_to_compute, computed_embeddings, embedding


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
