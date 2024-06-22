import backoff
from loguru import logger
import voyageai
import cohere
from sweepai.config.server import COHERE_API_KEY, VOYAGE_API_KEY
from sweepai.logn.cache import file_cache

@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=3,
    jitter=backoff.random_jitter,
)
@file_cache()
def cohere_rerank_call(
    query: str,
    documents: list[str],
    model='rerank-english-v3.0',
    **kwargs,
):
    # Cohere API call with caching
    co = cohere.Client(COHERE_API_KEY)
    try:
        return co.rerank(
            model=model,
            query=query,
            documents=documents,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Cohere rerank failed: {e}")
        raise e 

@file_cache()
def voyage_rerank_call(
    query: str,
    documents: list[str],
    model="rerank-1",
    **kwargs
):
    vo = voyageai.Client(api_key=VOYAGE_API_KEY)
    return vo.rerank(
        query, 
        documents, 
        model=model,
        **kwargs
    )

if __name__ == "__main__":
    query = "When is Apple's conference call scheduled?"
    documents = [
        "The Mediterranean diet emphasizes fish, olive oil, and vegetables, believed to reduce chronic diseases.",
        "Photosynthesis in plants converts light energy into glucose and produces essential oxygen.",
        "20th-century innovations, from radios to smartphones, centered on electronic advancements.",
        "Rivers provide water, irrigation, and habitat for aquatic species, vital for ecosystems.",
        "Apple’s conference call to discuss fourth fiscal quarter results and business updates is scheduled for Thursday, November 2, 2023 at 2:00 p.m. PT / 5:00 p.m. ET.",
        "Shakespeare's works, like 'Hamlet' and 'A Midsummer Night's Dream,' endure in literature."
    ]

    reranking = voyage_rerank_call(query, documents, model="rerank-lite-1", top_k=3)
    for r in reranking.results:
        print(f"Document: {r.document}")
        print(f"Relevance Score: {r.relevance_score}")
