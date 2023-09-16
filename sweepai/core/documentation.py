import asyncio
import re
from deeplake.core.vectorstore.deeplake_vectorstore import VectorStore
from loguru import logger
from logn import logn, LogTask
from tqdm import tqdm
from sweepai.core.lexical_search import prepare_index_from_docs, search_docs
from sweepai.core.robots import is_url_allowed
from sweepai.core.webscrape import webscrape
from sweepai.pre_indexed_docs import DOCS_ENDPOINTS

from sweepai.config.server import (
    ACTIVELOOP_TOKEN,
    DOCS_MODAL_INST_NAME,
    ENV,
    ORG_ID,
    SENTENCE_TRANSFORMERS_MODEL,
)

MODEL_DIR = "cache/model"
BATCH_SIZE = 128

timeout = 60 * 60  # 30 minutes


class ModalEmbeddingFunction:
    batch_size: int = 1024  # can pick a better constant later

    def __init__(self):
        pass

    def __call__(self, texts: list[str], cpu=False):
        if len(texts) == 0:
            return []
        return CPUEmbedding().compute(texts)  # pylint: disable=no-member


embedding_function = ModalEmbeddingFunction()


class CPUEmbedding:
    def __init__(self):
        from sentence_transformers import (  # pylint: disable=import-error
            SentenceTransformer,
        )

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
        )

    def compute(self, texts: list[str]) -> list[list[float]]:
        logn.info(f"Computing embeddings for {len(texts)} texts")
        vector = self.model.encode(texts, show_progress_bar=True, batch_size=BATCH_SIZE)
        if vector.shape[0] == 1:
            return [vector.tolist()]
        else:
            return vector.tolist()


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


@LogTask()
async def write_documentation(doc_url):
    try:
        url_allowed = is_url_allowed(doc_url, user_agent="*")
        ...
        return True
    except Exception as e:
        logger.error(f"Error occurred: {e}\n{traceback.format_exc()}")
        return False


async def daily_update():
    try:
        for doc_url, _ in DOCS_ENDPOINTS.values():
            await write_documentation(doc_url)
    except Exception as e:
        logger.error(f"Error occurred: {e}\n{traceback.format_exc()}")


def search_vector_store(doc_url, query, k=100):
    try:
        logn.info(f'Searching for "{query}" in {doc_url}')
        ...
        return final_urls, final_docs
    except Exception as e:
        logger.error(f"Error occurred: {e}\n{traceback.format_exc()}")
        return [], []
