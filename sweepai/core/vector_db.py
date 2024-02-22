from functools import lru_cache
import json
import multiprocessing
from typing import Generator
import backoff
from loguru import logger
from redis import Redis
from tqdm import tqdm
from sweepai.config.server import BATCH_SIZE, REDIS_URL, OPENAI_API_KEY
from sweepai.logn.cache import file_cache
from openai import OpenAI
import numpy as np

from sweepai.utils.hash import hash_sha256
from sweepai.utils.utils import Tiktoken

client = OpenAI()
CACHE_VERSION = "v1.0.16"
redis_client: Redis = Redis.from_url(REDIS_URL)
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

@file_cache(ignore_params=["texts"])
def get_query_texts_similarity(query: str, texts: str) -> float:
    embeddings = embed_text_array(texts)
    embeddings = np.concatenate(embeddings)
    query_embedding = embed_text_array([query])[0]
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
def embed_text_array(texts: tuple[str]):
    logger.info(
        f"Computing embeddings for {len(texts)} texts using openai..."
    )
    embeddings = []
    for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE), disable=False, desc="openai embedding"):
        try:
            embeddings.append(openai_with_expo_backoff(batch))
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.exception("Failed to get embeddings for batch")
            raise e
    return embeddings

def openai_call_embedding(batch):
    response = client.embeddings.create(
            input=batch, model="text-embedding-3-small", encoding_format="float"
    )
    cut_dim = np.array([data.embedding for data in response.data])[:, :512]
    normalized_dim = normalize_l2(cut_dim)
    # save results to redis
    return normalized_dim        

@backoff.on_exception(
            backoff.expo,
            Exception,
            max_tries=16,
        )
def openai_with_expo_backoff(batch: tuple[str]):
    if not redis_client:
        return openai_call_embedding(batch)
    # check cache first
    embeddings = [None] * len(batch)
    cache_keys = [hash_sha256(text) + CACHE_VERSION for text in batch]
    for i, cache_key in enumerate(cache_keys):
        try:
            cache_value = redis_client.get(cache_key)
            if cache_value:
                embeddings[i] = np.array(json.loads(cache_value))
        except Exception as e:
            logger.exception(e)
    # not stored in cache call openai
    batch = [text for i, text in enumerate(batch) if embeddings[i] is None] # remove all the cached values from the batch
    if len(batch) == 0:
        embeddings = np.array(embeddings)
        return embeddings # all embeddings are in cache
    try:
        new_embeddings = openai_call_embedding(batch)
    except Exception as e:
        # try to truncate the string and call openai again
        if any(tiktoken_client.count(text) > 8000 for text in batch):
            batch = [tiktoken_client.truncate_string(text) for text in batch]
            new_embeddings = openai_call_embedding(batch)
    # get all indices where embeddings are None
    indices = [i for i, emb in enumerate(embeddings) if emb is None]
    # store the new embeddings in the correct position
    assert len(indices) == len(new_embeddings)
    for i, index in enumerate(indices):
        embeddings[index] = new_embeddings[i]
    # store in cache
    for i, cache_key in enumerate(cache_keys):
        if embeddings[i] is not None:
            redis_client.set(cache_key, json.dumps(embeddings[i].tolist()))
    embeddings = np.array(embeddings)
    return embeddings
    
if __name__ == "__main__":
    texts = ["sasxt " * 10000 for i in range(10)] + ["abc " * 1 for i in range(10)]
    embeddings = embed_text_array(texts)