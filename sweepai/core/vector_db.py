import json
import multiprocessing
from typing import Generator

import backoff
import numpy as np
import requests
from loguru import logger
from redis import Redis
from tqdm import tqdm
import voyageai

from sweepai.config.server import BATCH_SIZE, REDIS_URL, VOYAGE_API_KEY
from sweepai.utils.hash import hash_sha256
from sweepai.utils.openai_proxy import get_embeddings_client
from sweepai.utils.utils import Tiktoken

CACHE_VERSION = "v2.0.04" # Now uses Voyage AI if available, asymmetric embedding
redis_client: Redis = Redis.from_url(REDIS_URL)  # TODO: add lazy loading
tiktoken_client = Tiktoken()


def cosine_similarity(a, B):
    dot_product = np.dot(B, a.T)  # B is MxN, a.T is Nx1, resulting in Mx1
    norm_a = np.linalg.norm(a)
    norm_B = np.linalg.norm(B, axis=1)
    return dot_product.flatten() / (norm_a * norm_B)  # Flatten to make it a 1D array


def chunk(texts: list[str], batch_size: int) -> Generator[list[str], None, None]:
    logger.info(f"Truncating {len(texts)} texts")
    texts = [text[:25000] if len(text) > 25000 else text for text in texts]
    # remove empty string
    texts = [text if text else " " for text in texts]
    logger.info(f"Finished truncating {len(texts)} texts")
    for i in range(0, len(texts), batch_size):
        yield texts[i : i + batch_size] if i + batch_size < len(texts) else texts[i:]


# @file_cache(ignore_params=["texts"])
def get_query_texts_similarity(query: str, texts: str) -> list[float]:
    if not texts:
        return []
    embeddings = embed_text_array(texts)
    embeddings = np.concatenate(embeddings)
    query_embedding = np.array(openai_call_embedding([query], input_type="query")[0])
    similarity = cosine_similarity(query_embedding, embeddings)
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


# lru_cache(maxsize=20)
# @redis_cache()
def embed_text_array(texts: tuple[str]) -> list[np.ndarray]:
    embeddings = []
    texts = [text if text else " " for text in texts]
    batches = [texts[i : i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
    workers = max(1, multiprocessing.cpu_count() // 4)
    if workers > 1 and not VOYAGE_API_KEY:
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
    return embeddings


# @redis_cache()
def openai_call_embedding(batch, input_type: str="document"): # input_type can be query or document
    if VOYAGE_API_KEY:
        client = voyageai.Client()
        result = client.embed(batch, model="voyage-code-2", input_type=input_type)
        cut_dim = np.array([data for data in result.embeddings])
        normalized_dim = normalize_l2(cut_dim)
        return normalized_dim
    client = get_embeddings_client()
    response = client.embeddings.create(
        input=batch, model="text-embedding-3-small", encoding_format="float"
    )
    cut_dim = np.array([data.embedding for data in response.data])[:, :512]
    normalized_dim = normalize_l2(cut_dim)
    # save results to redis
    return normalized_dim



@backoff.on_exception(
    backoff.expo,
    requests.exceptions.Timeout,
    max_tries=5,
)
def openai_with_expo_backoff(batch: tuple[str]):
    if not redis_client:
        return openai_call_embedding(batch)
    # check cache first
    embeddings = [None] * len(batch)
    cache_keys = [hash_sha256(text) + CACHE_VERSION for text in batch]
    try:
        for i, cache_value in enumerate(redis_client.mget(cache_keys)):
            if cache_value:
                embeddings[i] = np.array(json.loads(cache_value))
    except Exception as e:
        logger.exception(e)
    # not stored in cache call openai
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
        redis_client.mset(
            {
                cache_key: json.dumps(embedding.tolist())
                for cache_key, embedding in zip(cache_keys, embeddings)
            }
        )
        embeddings = np.array(embeddings)
    except Exception:
        # logger.error(str(e))
        # logger.error("Failed to store embeddings in cache, returning without storing")
        pass
    return embeddings


if __name__ == "__main__":
    texts = ["sasxtt " * 1000 for i in range(10)] + ["abb " * 1 for i in range(10)]
    embeddings = embed_text_array(texts)
