import json
import re
import time
from functools import lru_cache
from typing import Generator, List

import numpy as np
import replicate
import requests
from deeplake.core.vectorstore.deeplake_vectorstore import (  # pylint: disable=import-error
    VectorStore,
)
from loguru import logger
from redis import Redis
from sentence_transformers import SentenceTransformer  # pylint: disable=import-error
from tqdm import tqdm

def handle_redis_cache(redis_client, cache_key, compute_func, *args):
    """
    Helper function to handle Redis cache.
    It tries to get the value from the cache, if not found, it computes the value and sets it in the cache.
    """
    try:
        cache_value = redis_client.get(cache_key)
    except Exception as e:
        logger.exception(e)
        cache_value = None
    if cache_value is not None:
        return json.loads(cache_value)
    else:
        computed_value = compute_func(*args)
        redis_client.set(cache_key, json.dumps(computed_value))
        return computed_value

def log_info(message):
    """
    Helper function to handle logging of info messages.
    """
    logger.info(message)

def log_exception(message):
    """
    Helper function to handle logging of exceptions.
    """
    logger.exception(message)

def log_error(message):
    """
    Helper function to handle logging of error messages.
    """
    logger.error(message)

def handle_embeddings(texts, embed_func, *args):
    """
    Helper function to handle embeddings.
    It tries to compute the embeddings using the provided function.
    """
    try:
        return embed_func(texts, *args)
    except Exception:
        log_exception("Failed to get embeddings for batch")
        log_error(f"Failed to get embeddings for {texts}")
        return []

from sweepai.config.client import SweepConfig
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
from sweepai.core.entities import Snippet
from sweepai.core.lexical_search import prepare_index_from_snippets, search_index
from sweepai.core.repo_parsing_utils import repo_to_chunks
from sweepai.logn import file_cache
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
    model = handle_embeddings([SENTENCE_TRANSFORMERS_MODEL], SentenceTransformer, cache_folder=MODEL_DIR)

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
    return handle_embeddings(texts, _embed_huggingface)

def _embed_huggingface(texts):
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
            log_exception(
                f"Error occurred when sending request to Hugging Face endpoint: {e}"
            )


def embed_replicate(texts: List[str]) -> List[np.ndarray]:
    return handle_embeddings(texts, _embed_replicate)

def _embed_replicate(texts: List[str]) -> List[np.ndarray]:
    client = replicate.Client(api_token=REPLICATE_API_KEY)
    deployment = client.deployments.get(REPLICATE_DEPLOYMENT_URL)
    e = None
    for i in range(3):
        try:
            prediction = deployment.predictions.create(
                input={"text_batch": json.dumps(texts)}, timeout=60
            )
            prediction.wait()
            outputs = prediction.output
            break
        except Exception as e:
            log_exception(f"Replicate timeout: {e}")
    else:
        raise Exception(f"Replicate timeout")
    return [output["embedding"] for output in outputs]


@lru_cache(maxsize=64)
def embed_texts(texts: tuple[str]):
    log_info(
        log_info(f"Computing embeddings with {VECTOR_EMBEDDING_SOURCE}...")
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

        log_info(
            f"Found {len([x for x in embeddings if x is not None])} embeddings in cache"
        )
        indices_to_compute = [idx for idx, x in enumerate(embeddings) if x is None]
        documents_to_compute = [documents[idx] for idx in indices_to_compute]

        log_info(f"Computing {len(documents_to_compute)} embeddings...")
        computed_embeddings = embedding_function(documents_to_compute)
        log_info(f"Computed {len(computed_embeddings)} embeddings")

        for idx, embedding in zip(indices_to_compute, computed_embeddings):
            embeddings[idx] = embedding

        try:
            embeddings = np.array(embeddings, dtype=np.float32)
        except SystemExit:
            raise SystemExit
        except:
            log_exception(
                "Failed to convert embeddings to numpy array, recomputing all of them"
            )
            embeddings = embedding_function(documents)
            embeddings = np.array(embeddings, dtype=np.float32)

        deeplake_vs = init_deeplake_vs(collection_name)
        deeplake_vs.add(text=ids, embedding=embeddings, metadata=metadatas)
        log_info("Added embeddings to cache")
        if redis_client and len(documents_to_compute) > 0:
            log_info(f"Updating cache with {len(computed_embeddings)} embeddings")
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
        log_error("No documents found in repository")
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
    log_info("Getting query embedding...")
    query_embedding = embedding_function([query])  # pylint: disable=no-member
    log_info("Starting search by getting vector store...")
    deeplake_vs, lexical_index, num_docs = get_deeplake_vs_from_repo(
        cloned_repo, sweep_config=sweep_config
    )
    content_to_lexical_score = search_index(query, lexical_index)
    log_info(f"Found {len(content_to_lexical_score)} lexical results")
    log_info(f"Searching for relevant snippets... with {num_docs} docs")
    results = {"metadata": [], "text": []}
    try:
        results = deeplake_vs.search(embedding=query_embedding, k=num_docs)
    except SystemExit:
        raise SystemExit
    except Exception:
        log_exception("Exception occurred while fetching relevant snippets")
    log_info("Fetched relevant snippets...")
    if len(results["text"]) == 0:
        log_info(f"Results query {query} was empty")
        log_info(f"Results: {results}")
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
    log_info("Relevant paths: {}".format(relevant_paths[:5]))
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
