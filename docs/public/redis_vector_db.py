import hashlib
import json
import multiprocessing
import os
from typing import Generator

import backoff
import numpy as np
import requests
from loguru import logger
from openai import BadRequestError, OpenAI
from redis import Redis
from tiktoken import encoding_for_model

BATCH_SIZE = 512
REDIS_URL = os.environ.get("REDIS_URL", "redis://0.0.0.0:6379/0")
CACHE_VERSION = "v-2.0.1"
DIMENSIONS_TO_KEEP = 512

openai_client = OpenAI()
redis_client: Redis = Redis.from_url(REDIS_URL)

def count_tiktoken(text: str, model: str = "gpt-4") -> int:
    tiktoken_encoding = encoding_for_model(model)
    return len(tiktoken_encoding.encode(text, disallowed_special=()))

def truncate_string_tiktoken(text: str, model: str = "gpt-4", max_tokens: int = 8192) -> str:
    tiktoken_encoding = encoding_for_model(model)
    tokens = tiktoken_encoding.encode(text)[:max_tokens]
    return tiktoken_encoding.decode(tokens)

def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

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

def embed_text_array(texts: tuple[str]) -> list[np.ndarray]:
    embeddings = []
    texts = [text if text else " " for text in texts]
    batches = [texts[i : i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
    with multiprocessing.Pool() as pool:
        embeddings = pool.map(openai_with_expo_backoff, batches)
    return embeddings

def openai_call_embedding(batch):
    response = openai_client.embeddings.create(
        input=batch, model="text-embedding-3-small", encoding_format="float"
    )
    cut_dim = np.array([data.embedding for data in response.data])[:, :DIMENSIONS_TO_KEEP]
    normalized_dim = normalize_l2(cut_dim)
    return normalized_dim

@backoff.on_exception(
    backoff.expo,
    requests.exceptions.Timeout,
    max_tries=5,
)
def openai_with_expo_backoff(batch: tuple[str]):
    # 0. If we don't have a redis client, just call openai
    if not redis_client:
        return openai_call_embedding(batch)
    # 1. Get embeddings from redis, using the hash of the text as the key
    embeddings: list[np.ndarray] = [None] * len(batch)
    cache_keys = [hash_text(text) + CACHE_VERSION for text in batch]
    try:
        for i, cache_value in enumerate(redis_client.mget(cache_keys)):
            if cache_value:
                embeddings[i] = np.array(json.loads(cache_value))
    except Exception as e:
        logger.exception(f"Failure in openai_with_expo_backoff: {e}")
    # 2. If we have all the embeddings, return them
    batch = [text for idx, text in enumerate(batch) if isinstance(embeddings[idx], type(None))]
    if len(batch) == 0:
        embeddings = np.array(embeddings)
        return embeddings
    # 3. If we don't have all the embeddings, call openai for the missing ones
    try:
        new_embeddings = openai_call_embedding(batch)
    except requests.exceptions.Timeout as e:
        logger.exception(f"Timeout error occured while embedding: {e}")
    except BadRequestError as e:
        try:
            # 4. If we get a BadRequestError, truncate the text and try again
            batch = [truncate_string_tiktoken(text) for text in batch] # truncation is slow, so we only do it if we have to
            new_embeddings = openai_call_embedding(batch)
        except Exception as e:
            logger.exception(f"Failure calling openai_call_embedding: {e}")
    # 5. Place the new embeddings in the correct position
    indices = [i for i, emb in enumerate(embeddings) if emb is None]
    for i, index in enumerate(indices):
        embeddings[index] = new_embeddings[i]
    # 6. Store the new embeddings in redis
    redis_client.mset(
        {
            cache_key: json.dumps(embedding.tolist())
            for cache_key, embedding in zip(cache_keys, embeddings)
        }
    )
    return np.array(embeddings)

def get_query_text_similarity(query: str, texts: str) -> float:
    embeddings = embed_text_array(texts)
    embeddings = np.concatenate(embeddings)
    query_embedding = embed_text_array([query])[0]
    similarity = np.dot(embeddings, query_embedding.T).flatten()
    similarity = similarity.tolist()
    return similarity

def get_most_similar_texts(query: str, texts: list[str], top_n: int = 5) -> list[str]:
    similarity = get_query_text_similarity(query, texts)
    indices = np.argsort(similarity)[::-1]
    return [texts[i] for i in indices[:top_n]]

if __name__ == "__main__":
    import time
    start = time.time()
    n = 30000
    query = "example_query"
    document = "example_document"
    texts = [document for _ in range(n)]
    most_similar_texts = get_most_similar_texts(query, texts)
    elapsed = time.time() - start
    # elapsed in ms
    print(f"Elapsed: {elapsed * 1000}ms")