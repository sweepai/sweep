
import cohere
from sweepai.config.server import COHERE_API_KEY
from sweepai.logn.cache import file_cache


@file_cache()
def cohere_rerank_call(
    query: str,
    documents: list[str],
    model='rerank-english-v3.0',
    **kwargs,
):
    # Cohere API call with caching
    co = cohere.Client(COHERE_API_KEY)
    return co.rerank(
        model=model,
        query=query,
        documents=documents,
        **kwargs
    )