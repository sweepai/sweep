import json
import os
import re
import time
import shutil
import glob

from modal import stub
from loguru import logger
from redis import Redis
from tqdm import tqdm
import modal
from modal import method
from deeplake.core.vectorstore.deeplake_vectorstore import DeepLakeVectorStore
from github import Github
from git import Repo

from sweepai.core.entities import Snippet
from sweepai.utils.event_logger import posthog
from sweepai.utils.hash import hash_sha256
from sweepai.utils.scorer import compute_score, convert_to_percentiles

from ..utils.github_utils import get_token
from ..utils.constants import DB_NAME, BOT_TOKEN_NAME, ENV, UTILS_NAME
from ..utils.config import SweepConfig
import time

# TODO: Lots of cleanups can be done here with these constants
stub = modal.Stub(DB_NAME)
chunker = modal.Function.lookup(UTILS_NAME, "Chunking.chunk")
model_volume = modal.SharedVolume().persist(f"{ENV}-storage")
MODEL_DIR = "/root/cache/model"
DEEPLAKE_DIR = "/root/cache/"
DISKCACHE_DIR = "/root/cache/diskcache/"
DEEPLAKE_FOLDER = "deeplake/"
BATCH_SIZE = 256
SENTENCE_TRANSFORMERS_MODEL = "sentence-transformers/all-MiniLM-L12-v2"
timeout = 60 * 30 # 30 minutes
CACHE_VERSION = "v1.0.0"
MAX_FILES = 3000

image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install("deeplake==3.6.3", "sentence-transformers")
    .pip_install("openai", "PyGithub", "loguru", "docarray", "GitPython", "tqdm", "highlight-io", "anthropic", "posthog", "redis", "pyyaml")
)
secrets = [
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name("huggingface"),
    modal.Secret.from_name("chroma-endpoint"),
    modal.Secret.from_name("posthog"),
    modal.Secret.from_name("highlight"),
    modal.Secret.from_name("redis_url"),
    modal.Secret.from_dict({"TRANSFORMERS_CACHE": MODEL_DIR}),
]

def init_deeplake_vs(repo_name):
    deeplake_repo_path = f"mem://{DEEPLAKE_FOLDER}{repo_name}"
    deeplake_vector_store = DeepLakeVectorStore(path = deeplake_repo_path)
    return deeplake_vector_store

def parse_collection_name(name: str) -> str:
    # Replace any non-alphanumeric characters with hyphens
    name = re.sub(r"[^\w-]", "--", name)
    # Ensure the name is between 3 and 63 characters and starts/ends with alphanumeric
    name = re.sub(r"^(-*\w{0,61}\w)-*$", r"\1", name[:63].ljust(3, "x"))
    return name

def get_deeplake_vs_from_repo(
    repo_name: str,
    sweep_config: SweepConfig = SweepConfig(),
    installation_id: int = None,
    branch_name: str = None,
):
    deeplake_vs = get_deeplake_vs_from_repo(
        repo_name=repo_name, installation_id=installation_id, sweep_config=sweep_config
    )
    results = {"metadata": [], "text": []}
    for n_result in range(n_results, 0, -1):
        try:
            query_embedding = embedding_function([query])[0]
            results = deeplake_vs.search(embedding=query_embedding, k=n_result)
            break
        except Exception:
            pass
    if len(results["text"]) == 0:
        if username is None:
            username = "anonymous"
        posthog.capture(
            username,
            "failed",
            {
                "reason": "Results query was empty",
                "repo_name": repo_name,
                "installation_id": installation_id, 
                "query": query, 
                "n_results": n_results
            },
        )
    metadatas = results["metadata"]
    code_scores = [metadata["score"] for metadata in metadatas]
    vector_scores = results["score"]
    combined_scores = [code_score + vector_score for code_score, vector_score in zip(code_scores, vector_scores)]
    # Sort by combined scores
    # Combine the three lists into a single list of tuples
    combined_list = list(zip(combined_scores, metadatas))

    # Sort the combined list based on the combined scores
    sorted_list = sorted(combined_list, key=lambda x: x[0], reverse=True)

    # Extract the sorted metadatas and relevant_paths
    sorted_metadatas = [metadata for _, metadata in sorted_list]
    relevant_paths = [metadata["file_path"] for metadata in sorted_metadatas]
    logger.info("Relevant paths: {}".format(relevant_paths))
    return [
        Snippet(
            content="",
            start=metadata["start"], 
            end=metadata["end"], 
            file_path=file_path
        ) for metadata, file_path in zip(sorted_metadatas, relevant_paths)
    ]

