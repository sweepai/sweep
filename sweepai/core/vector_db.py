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
from sweepai.utils.utils import Tiktoken

from sweepai.utils.hash import hash_sha256
client = OpenAI()
CACHE_VERSION = "v1.0.14"
redis_client = Redis.from_url(REDIS_URL)

def cosine_similarity(a, B):
    dot_product = np.dot(B, a.T)  # B is MxN, a.T is Nx1, resulting in Mx1
    norm_a = np.linalg.norm(a)
    norm_B = np.linalg.norm(B, axis=1)
    return dot_product.flatten() / (norm_a * norm_B)  # Flatten to make it a 1D array


def chunk(texts: list[str], batch_size: int) -> Generator[list[str], None, None]:
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

def string_to_embedding(batch: list[str]):
    tik_token_client = Tiktoken()
    batch = [tik_token_client.truncate_string(text) for text in batch] # truncate string
    return openai_with_expo_backoff(batch)

# lru_cache(maxsize=20)
def embed_text_array(texts: tuple[str]):
    logger.info(
        f"Computing embeddings for {len(texts)} texts using openai..."
    )
    embeddings = []
    with multiprocessing.Pool(processes=8) as p:
        for embedding in tqdm(
            p.imap(string_to_embedding, 
            [batch for batch in chunk(texts, batch_size=BATCH_SIZE)]), 
            disable=False, 
            desc="openai embedding"
        ):
            try:
                embeddings.append(embedding)
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.exception("Failed to get embeddings for batch")
                raise e
    return embeddings
        
@backoff.on_exception(
            backoff.expo,
            Exception,
            max_tries=16,
        )
def openai_with_expo_backoff(batch: tuple[str]):
    # check cache first
    if redis_client:
        cache_key = hash_sha256("".join(batch)) + CACHE_VERSION
    try:
        if redis_client:
            cache_value = redis_client.get(cache_key)
            if cache_value:
                score_factor = np.array(json.loads(cache_value))
                return score_factor
    except Exception as e:
        logger.exception(e)
        cache_value = None
    # not stored in cache call openai
    try:
        response = client.embeddings.create(
                        input=batch, model="text-embedding-3-small", encoding_format="float"
                    )
        cut_dim = np.array([data.embedding for data in response.data])[:, :512]
        normalized_dim = normalize_l2(cut_dim)
        if redis_client:
            redis_client.set(cache_key, json.dumps(normalized_dim.tolist()))
        # save results to redis
        return normalized_dim
    except Exception as e:
        raise e
    
if __name__ == "__main__":
    texts = ["sample text " * 10000 for i in range(BATCH_SIZE * 2)]
    embeddings = embed_text_array(texts)