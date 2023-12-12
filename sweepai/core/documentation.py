import os
import re

from deeplake.core.vectorstore.deeplake_vectorstore import VectorStore

from sweepai.config.server import ACTIVELOOP_TOKEN, ORG_ID
from sweepai.core.lexical_search import prepare_index_from_docs, search_docs
from sweepai.core.robots import is_url_allowed
from sweepai.core.vector_db import embed_texts
from sweepai.core.webscrape import webscrape
from sweepai.logn import logger
from sweepai.pre_indexed_docs import DOCS_ENDPOINTS

MODEL_DIR = "/tmp/cache/model"
BATCH_SIZE = 128
timeout = 60 * 60  # 30 minutes


def embedding_function(texts: list[str]):
    # For LRU cache to work
    return embed_texts(tuple(texts))


def chunk_string(s):
    # Chunker's terrible, can be improved later

    # Split the string into sentences
    sentences = re.split(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s", s)

    # If there are fewer sentences than a chunk size, return the whole string as a single chunk
    if len(sentences) <= 6:
        return [s]

    chunks = []
    i = 0

    # Slide a window of 6 sentences, moving it by 4 sentences each time
    while i < len(sentences):
        chunks.append(" ".join(sentences[i : i + 6]))
        i += 4
    return chunks


def remove_non_alphanumeric(url):
    # Keep only alphanumeric characters, and remove all others
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", url)
    return cleaned


def write_documentation(doc_url: str) -> bool:
    try:
        url_allowed = is_url_allowed(doc_url, user_agent="*")
        if not url_allowed:
            logger.info(f"URL {doc_url} is not allowed")
            return False
        idx_name = remove_non_alphanumeric(doc_url)
        if not ACTIVELOOP_TOKEN:
            path = f"sweep_docs/{idx_name}"
            if os.path.exists(path):
                logger.info(f"Path {path} already exists, not writing docs")
                return True
            vector_store = VectorStore(
                path=path,
                overwrite=True,
            )
        else:
            vector_store = VectorStore(
                path=f"hub://{ORG_ID}/{idx_name}",
                runtime={"tensor_db": True},
                overwrite=True,
                token=ACTIVELOOP_TOKEN,
            )
        url_to_documents = webscrape(doc_url)
        urls, document_chunks = [], []
        for url, document in url_to_documents.items():
            if len(document) == 0:
                logger.info(f"Empty document for url {url}")
            document_chunks.extend(chunk_string(document))
            urls.extend([url] * len(chunk_string(document)))
        computed_embeddings = embedding_function(document_chunks)
        vector_store.add(
            text=document_chunks,
            embedding=computed_embeddings,
            metadata=[{"url": url} for url in urls],
        )
        return True
    except Exception as e:
        logger.error(f"Error writing documentation: {e}")
        return False


def daily_update() -> None:
    for doc_url, _ in DOCS_ENDPOINTS.values():
        write_documentation(doc_url)


def search_vector_store(doc_url, query, k=100):
    logger.info(f'Searching for "{query}" in {doc_url}')
    idx_name = remove_non_alphanumeric(doc_url)
    if not ACTIVELOOP_TOKEN:
        vector_store = VectorStore(
            path=f"sweep_docs/{idx_name}",
            read_only=True,
        )
    else:
        vector_score = VectorStore(
            path=f"hub://{ORG_ID}/{idx_name}",
            runtime={"tensor_db": True},
            read_only=True,
            token=ACTIVELOOP_TOKEN,
        )
    logger.info("Embedding query...")
    query_embedding = embedding_function([query])
    logger.info("Searching vector store...")
    results = vector_store.search(embedding=query_embedding, k=k)
    metadatas = results["metadata"]
    docs = results["text"]
    vector_scores = results["score"]
    url_and_docs = [(metadata["url"], doc) for metadata, doc in zip(metadatas, docs)]
    ix = prepare_index_from_docs(url_and_docs)
    docs_to_scores = search_docs(query, ix)
    max_score = max(docs_to_scores.values())
    min_score = (
        min(docs_to_scores.values()) if min(docs_to_scores.values()) < max_score else 0
    )
    max_vector_score = max(vector_scores)
    min_vector_score = (
        min(vector_scores) if min(vector_scores) < max_vector_score else 0
    )
    text_to_final_score = []
    for idx, (url, doc) in enumerate(url_and_docs):
        lexical_score = docs_to_scores[url] if url in docs_to_scores else 0
        vector_score = vector_scores[idx]
        normalized_lexical_score = (lexical_score - (min_score / 2)) / (
            (max_score + min_score)
        )
        normalized_vector_score = (vector_score - (min_vector_score / 2)) / (
            (max_vector_score + min_vector_score)
        )
        final_score = normalized_lexical_score * normalized_vector_score
        text_to_final_score.append((url, doc, final_score))
    sorted_docs = sorted(text_to_final_score, key=lambda x: x[-1], reverse=True)
    sorted_docs = [(url, doc) for url, doc, _ in sorted_docs]
    # get docs until you reach a 20k character count
    final_docs = []
    final_urls = []
    for url, doc in sorted_docs:
        if url not in final_urls and len("".join(final_docs)) + len(doc) < 20000:
            final_docs.append(doc)
            final_urls.append(url)
        elif len("".join(final_docs)) + len(doc) > 20000:
            break
    logger.info("Done searching vector store")
    return final_urls, final_docs
