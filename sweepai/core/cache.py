import json
import numpy as np
from redis import Redis
from sweepai.utils.hash import hash_sha256

def get_redis_client():
    REDIS_URL = "redis://localhost:6379/0"
    return Redis.from_url(REDIS_URL)

def update_cache_with_embeddings(documents_to_compute, computed_embeddings):
    SENTENCE_TRANSFORMERS_MODEL = "all-MiniLM-L6-v2"
    VECTOR_EMBEDDING_SOURCE = "sentence-transformers"
    CACHE_VERSION = "v1.0.13"
    redis_client = get_redis_client()
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
