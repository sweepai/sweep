import json
import multiprocessing
import os
from typing import Generator

import backoff
from diskcache import Cache
import numpy as np
import openai
import requests
from loguru import logger
from scipy.spatial.distance import cdist

from tqdm import tqdm
import voyageai
import boto3
from botocore.exceptions import ClientError
from voyageai import error as voyageai_error

from sweepai.utils.timer import Timer
from sweepai.config.server import BATCH_SIZE, CACHE_DIRECTORY, VOYAGE_API_AWS_ENDPOINT_NAME, VOYAGE_API_KEY, VOYAGE_API_USE_AWS
from sweepai.utils.hash import hash_sha256
from sweepai.utils.openai_proxy import get_embeddings_client
from sweepai.utils.tiktoken_utils import Tiktoken

# Now uses Voyage AI if available, with asymmetric embedding
# CACHE_VERSION = "v2.0.04" + "-voyage" if VOYAGE_API_KEY else ""
suffix = "-voyage-aws" if VOYAGE_API_USE_AWS else "-voyage" if VOYAGE_API_KEY else ""
CACHE_VERSION = "v2.1.1" + suffix 
tiktoken_client = Tiktoken()
vector_cache = Cache(f'{CACHE_DIRECTORY}/vector_cache') # we instantiate a singleton, diskcache will handle concurrency


def cosine_similarity(a, B):
    # use scipy
    return 1 - cdist(a, B, metric='cosine')


def chunk(texts: list[str], batch_size: int) -> Generator[list[str], None, None]:
    logger.info(f"Truncating {len(texts)} texts")
    texts = [text[:25000] if len(text) > 25000 else text for text in texts]
    # remove empty string
    texts = [text if text else " " for text in texts]
    logger.info(f"Finished truncating {len(texts)} texts")
    for i in range(0, len(texts), batch_size):
        yield texts[i : i + batch_size] if i + batch_size < len(texts) else texts[i:]


# @file_cache(ignore_params=["texts"])
def multi_get_query_texts_similarity(queries: list[str], documents: list[str]) -> list[float]:
    if not documents:
        return []
    embeddings = embed_text_array(documents)
    embeddings = np.concatenate(embeddings)
    with Timer() as timer:
        query_embedding = np.array(openai_call_embedding(queries, input_type="query"))
    logger.info(f"Embedding query took {timer.time_elapsed:.2f} seconds")
    with Timer() as timer:
        similarity = cosine_similarity(query_embedding, embeddings)
    logger.info(f"Similarity took {timer.time_elapsed:.2f} seconds")
    similarity = similarity.tolist()
    return similarity


def normalize_l2(x):
    x = np.array(x)
    if x.ndim == 1:
        norm = np.linalg.norm(x)
        if norm == 0:
            return x
        return x / norm
    else:
        norm = np.linalg.norm(x, 2, axis=1, keepdims=True)
        return np.where(norm == 0, x, x / norm)

def batch_by_token_count_for_voyage(
    texts: list[str],
    max_tokens: int = 120_000,
    max_length: int = 128,
) -> list[list[str]]:
    """
    This function splits the texts into batches based on the token count.
    Max token count for Voyage is 120k and max batch length count is 128.
    """
    client = voyageai.Client()
    batches = []
    batch = []
    token_count = 0
    for text in texts:
        text_token_count = client.count_tokens([text])
        if token_count + text_token_count > max_tokens * 0.95 or len(batch) >= max_length:
            batches.append(batch)
            batch = [text]  # Start the new batch with the current text
            token_count = text_token_count  # Reset token count for the new batch
        else:
            batch.append(text)
            token_count += text_token_count
    if batch:
        batches.append(batch)
    del client
    return batches

# lru_cache(maxsize=20)
# @redis_cache()
def embed_text_array(texts: list[str]) -> list[np.ndarray]:
    embeddings = []
    texts = [text if text else " " for text in texts]
    batches = [texts[i : i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
    workers = min(max(1, multiprocessing.cpu_count() // 4), 1)
    with Timer() as timer:
        if workers > 1 and len(batches) > 1:
            with multiprocessing.Pool(
                processes=workers
            ) as pool:
                embeddings = list(
                    tqdm(
                        pool.imap(openai_with_expo_backoff, batches),
                        total=len(batches),
                        desc="openai embedding",
                    )
                )
        else:
            embeddings = [openai_with_expo_backoff(batch) for batch in tqdm(batches, desc="openai embedding")]
    logger.info(f"Embedding docs took {timer.time_elapsed:.2f} seconds")
    return embeddings


# @redis_cache()
def openai_call_embedding_router(batch: list[str], input_type: str="document"): # input_type can be query or document
    VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", None)
    VOYAGE_API_AWS_ACCESS_KEY = os.environ.get("VOYAGE_API_AWS_ACCESS_KEY", None)
    VOYAGE_API_AWS_SECRET_KEY = os.environ.get("VOYAGE_API_AWS_SECRET_KEY", None)
    VOYAGE_API_AWS_REGION = os.environ.get("VOYAGE_API_AWS_REGION", None)
    VOYAGE_API_USE_AWS = VOYAGE_API_AWS_ACCESS_KEY and VOYAGE_API_AWS_SECRET_KEY and VOYAGE_API_AWS_REGION
    if len(batch) == 0:
        return np.array([])
    if VOYAGE_API_USE_AWS:
        sm_runtime = boto3.client(
            "sagemaker-runtime",
            aws_access_key_id=VOYAGE_API_AWS_ACCESS_KEY,
            aws_secret_access_key=VOYAGE_API_AWS_SECRET_KEY,
            region_name=VOYAGE_API_AWS_REGION
        )
        input_json = json.dumps({
            "input": batch,
            "input_type": input_type, 
            "truncation": "true"
        })
        response = sm_runtime.invoke_endpoint(
            EndpointName=VOYAGE_API_AWS_ENDPOINT_NAME,
            ContentType="application/json",
            Accept="application/json",
            Body=input_json,
        )
        body = response["Body"]
        obj = json.load(body)
        data = obj["data"]
        return np.array([vector["embedding"] for vector in data])
    elif VOYAGE_API_KEY:
        client = voyageai.Client(api_key=VOYAGE_API_KEY)
        result = client.embed(batch, model="voyage-code-2", input_type=input_type, truncation=True)
        cut_dim = np.array([data for data in result.embeddings])
        normalized_dim = normalize_l2(cut_dim)
        del client
        return normalized_dim
    else:
        client = get_embeddings_client()
        response = client.embeddings.create(
            input=batch, model="text-embedding-3-small", encoding_format="float"
        )
        cut_dim = np.array([data.embedding for data in response.data])[:, :512]
        normalized_dim = normalize_l2(cut_dim)
        # save results to redis
        return normalized_dim

def openai_call_embedding(batch: list[str], input_type: str="document"):
    # Backoff on batch size by splitting the batch in half.
    try:
        return openai_call_embedding_router(batch, input_type)
    except (voyageai_error.InvalidRequestError, ClientError) as e: # full error is botocore.errorfactory.ModelError: but I can't find it
        if len(batch) > 1 and "Please lower the number of tokens in the batch." in str(e):
            logger.error(f"Token count exceeded for batch: {max([tiktoken_client.count(text) for text in batch])} retrying by splitting batch in half.")
            mid = len(batch) // 2
            left = openai_call_embedding(batch[:mid], input_type)
            right = openai_call_embedding(batch[mid:], input_type)
            return np.concatenate((left, right))
        else:
            raise e
    except openai.BadRequestError as e:
        # In the future we can better handle this by averaging the embeddings of the split batch
        if "maximum context length" in str(e):
            logger.warning(f"Token count exceeded for batch: {max([tiktoken_client.count(text) for text in batch])} truncating down to 8192 tokens.")
            batch = [tiktoken_client.truncate_string(text) for text in batch]
            return openai_call_embedding(batch, input_type)


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.Timeout,
    max_tries=5,
)
def openai_with_expo_backoff(batch: tuple[str]):
    # check cache first
    embeddings: list[np.ndarray | None] = [None] * len(batch)
    cache_keys = [hash_sha256(text) + CACHE_VERSION for text in batch]

    try:
        for i, cache_key in enumerate(cache_keys):
            cache_value = vector_cache.get(cache_key)
            if cache_value is not None:
                embeddings[i] = cache_value
    except Exception as e:
        logger.warning(f"Error reading embeddings from cache: {e}")

    # not stored in cache, call openai
    batch = [
        text for i, text in enumerate(batch) if embeddings[i] is None
    ]  # remove all the cached values from the batch
    if len(batch) == 0:
        embeddings = np.array(embeddings)
        return embeddings  # all embeddings are in cache
    try:
        # make sure all token counts are within model params (max: 8192)
        new_embeddings = openai_call_embedding(batch)
    except requests.exceptions.Timeout as e:
        logger.exception(f"Timeout error occured while embedding: {e}")
    except Exception as e:
        logger.exception(e)
        if any(tiktoken_client.count(text) > 8192 for text in batch):
            logger.warning(
                f"Token count exceeded for batch: {max([tiktoken_client.count(text) for text in batch])} truncating down to 8192 tokens."
            )
            batch = [tiktoken_client.truncate_string(text) for text in batch]
            new_embeddings = openai_call_embedding(batch)
        else:
            raise e
    # get all indices where embeddings are None
    indices = [i for i, emb in enumerate(embeddings) if emb is None]
    # store the new embeddings in the correct position
    assert len(indices) == len(new_embeddings)
    for i, index in enumerate(indices):
        embeddings[index] = new_embeddings[i]
    # store in cache
    try:
        for cache_key, embedding in zip(cache_keys, embeddings):
            vector_cache.set(cache_key, embedding)
        embeddings = np.array(embeddings)
    except Exception as e:
        logger.warning(f"Error storing embeddings in cache: {e}")
    return embeddings


if __name__ == "__main__":
    texts = ["sasxtt " * 10000 for i in range(10)] + ["abb " * 1 for i in range(10)]
    embeddings = embed_text_array(texts)
