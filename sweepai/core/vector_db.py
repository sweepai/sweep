import glob
import json
import os
import re
import shutil
import time

import modal
from git.repo import Repo
from github import Github
from loguru import logger
from modal import method
from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from redis.exceptions import (
   BusyLoadingError,
   ConnectionError,
   TimeoutError
)
from tqdm import tqdm

from sweepai.core.entities import Snippet
from sweepai.utils.event_logger import posthog
from sweepai.utils.hash import hash_sha256
from sweepai.utils.scorer import get_factors, get_scores
from sweepai.config.client import SweepConfig
from sweepai.config.server import ENV, DB_MODAL_INST_NAME, UTILS_MODAL_INST_NAME, REDIS_URL, BOT_TOKEN_NAME
from ..utils.github_utils import get_token


stub = modal.Stub(DB_MODAL_INST_NAME)
chunker = modal.Function.lookup(UTILS_MODAL_INST_NAME, "chunk")
model_volume = modal.NetworkFileSystem.persisted(f"{ENV}-storage")
MODEL_DIR = "/root/cache/model"
DEEPLAKE_DIR = "/root/cache/"
DISKCACHE_DIR = "/root/cache/diskcache/"
DEEPLAKE_FOLDER = "deeplake/"
BATCH_SIZE = 128
SENTENCE_TRANSFORMERS_MODEL = "thenlper/gte-base"
timeout = 60 * 60  # 30 minutes
CACHE_VERSION = "v1.0.9"
MAX_FILES = 500
CPU = 0.5

def download_models():
    from sentence_transformers import SentenceTransformer # pylint: disable=import-error

    model = SentenceTransformer(
        SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
    )

image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install("deeplake==3.6.17", "sentence-transformers")
    .pip_install("openai", "PyGithub", "loguru", "docarray", "GitPython", "tqdm", "anthropic",
                 "posthog", "redis", "pyyaml")
    .run_function(download_models)
)
secrets = [
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("github"),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name("huggingface"),
    modal.Secret.from_name("chroma-endpoint"),
    modal.Secret.from_name("posthog"),
    modal.Secret.from_name("redis_url"),
    modal.Secret.from_dict({"TRANSFORMERS_CACHE": MODEL_DIR}),
]


def init_deeplake_vs(repo_name):
    from deeplake.core.vectorstore.deeplake_vectorstore import DeepLakeVectorStore # pylint: disable=import-error
    deeplake_repo_path = f"mem://{DEEPLAKE_FOLDER}{repo_name}"
    deeplake_vector_store = DeepLakeVectorStore(path=deeplake_repo_path)
    return deeplake_vector_store


def parse_collection_name(name: str) -> str:
    # Replace any non-alphanumeric characters with hyphens
    name = re.sub(r"[^\w-]", "--", name)
    # Ensure the name is between 3 and 63 characters and starts/ends with alphanumeric
    name = re.sub(r"^(-*\w{0,61}\w)-*$", r"\1", name[:63].ljust(3, "x"))
    return name


@stub.cls(
    image=image,
    secrets=secrets,
    network_file_systems={MODEL_DIR: model_volume},
    keep_warm=1 if ENV == "prod" else 0,
    gpu="T4",
    retries=modal.Retries(
        max_retries=5, backoff_coefficient=2, initial_delay=5),
    timeout=timeout,
)
class Embedding:

    def __enter__(self):
        from sentence_transformers import SentenceTransformer # pylint: disable=import-error

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
        )

    @method()
    def compute(self, texts: list[str]):
        logger.info(f"Computing embeddings for {len(texts)} texts")
        vector = self.model.encode(texts, show_progress_bar=True, batch_size=BATCH_SIZE).tolist()
        try:
            logger.info(f'{len(vector)}\n{len(vector[0])}')
        except Exception as e:
            print(f'oops {e}')
            pass
        return vector

@stub.cls(
    image=image,
    secrets=secrets,
    network_file_systems={MODEL_DIR: model_volume},
    keep_warm=1,
    retries=modal.Retries(max_retries=5, backoff_coefficient=2, initial_delay=5),
    cpu=2, # this can change later
    timeout=timeout,
)
class CPUEmbedding:
    def __enter__(self):
        from sentence_transformers import SentenceTransformer # pylint: disable=import-error

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
        )

    @method()
    def compute(self, texts: list[str]) -> list[list[float]]:
        logger.info(f"Computing embeddings for {len(texts)} texts")
        vector = self.model.encode(texts, show_progress_bar=True, batch_size=BATCH_SIZE).tolist()
        try:
            logger.info(f'{len(vector)}\n{len(vector[0])}')
        except Exception as e:
            logger.info(f'oops {e}')
            pass
        return vector


class ModalEmbeddingFunction:
    batch_size: int = 4096 # can pick a better constant later

    def __init__(self):
        pass

    def __call__(self, texts: list[str], cpu=False):
        if len(texts) == 0:
            return []
        if cpu or len(texts) < 10: 
            return CPUEmbedding.compute.call(texts) # pylint: disable=no-member
        else:
            batches = [texts[i:i + ModalEmbeddingFunction.batch_size] for i in range(0, len(texts), ModalEmbeddingFunction.batch_size)]
            batches = [batch for batch in batches if len(batch) > 0]
            logger.info([len(batch) for batch in batches])
            results = []
            for batch in tqdm(Embedding.compute.map(batches)): # pylint: disable=no-member
                results.extend(batch)

            return results

embedding_function = ModalEmbeddingFunction()


def get_deeplake_vs_from_repo(
        repo_name: str,
        installation_id: int,
        branch_name: str | None = None,
        sweep_config: SweepConfig = SweepConfig(),
):
    token = get_token(installation_id)
    g = Github(token)
    repo = g.get_repo(repo_name)
    commits = repo.get_commits()
    commit_hash = commits[0].sha

    cache_success = False
    cache_inst = None

    if REDIS_URL is not None:
        try:
            # todo: initialize once
            retry = Retry(ExponentialBackoff(), 3)
            cache_inst = Redis.from_url(REDIS_URL, retry=retry, retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError])
            logger.info(f"Successfully connected to redis cache")
            cache_success = True
        except:
            cache_success = False
            logger.error(f"Failed to connect to redis cache")
    else:
        logger.warning(f"REDIS_URL is None, skipping cache")

    if cache_inst and cache_success:

        try:
            github_cache_key = f"github-{commit_hash}{CACHE_VERSION}"
            cache_hit = cache_inst.get(github_cache_key)
            if cache_hit:
                deeplake_items = json.loads(cache_hit)
                logger.info(f"Cache hit for {repo_name}")
            else:
                deeplake_items = None
                logger.info(f"Cache miss for {repo_name}")

            if deeplake_items:
                deeplake_vs = init_deeplake_vs(repo_name)
                deeplake_vs.add(
                    text=deeplake_items['ids'],
                    embedding=deeplake_items['embeddings'],
                    metadata=deeplake_items['metadatas']
                )
                logger.info(f"Returning deeplake vs for {repo_name}")
                return deeplake_vs
            else:
                logger.info(f"Cache for {repo_name} is empty")
        except:
            logger.info(f"Failed to get cache for {repo_name}")
    logger.info(f"Downloading repository and indexing for {repo_name}...")
    start = time.time()
    logger.info("Recursively getting list of files...")

    repo_url = f"https://x-access-token:{token}@github.com/{repo_name}.git"
    shutil.rmtree("repo", ignore_errors=True)

    branch_name = SweepConfig.get_branch(repo)

    git_repo = Repo.clone_from(repo_url, "repo")
    git_repo.git.checkout(branch_name)

    file_list = glob.iglob("repo/**", recursive=True)
    file_list = [
        file
        for file in tqdm(file_list)
        if os.path.isfile(file)
           and all(not file.endswith(ext) for ext in sweep_config.exclude_exts)
           and all(not file[len("repo/"):].startswith(dir_name) for dir_name in sweep_config.exclude_dirs)
    ]
    logger.info(f"First pass through files complete, found {len(file_list)} files")
    file_paths = []
    file_contents = []
    score_factors = []

    for file in tqdm(file_list):
        with open(file, "rb") as f:
            is_binary = False
            for block in iter(lambda: f.read(1024), b''):
                if b'\0' in block:
                    is_binary = True
                    break
            if is_binary:
                logger.debug("Skipping binary file...")
                continue

        with open(file, "rb") as f:
            if len(f.read()) > sweep_config.max_file_limit:
                logger.debug("Skipping large file...")
                continue

        with open(file, "r") as f:
            # Can parallelize this
            try:
                contents = f.read()
                contents = file + contents
            except UnicodeDecodeError as e:
                logger.warning(f"Received warning {e}, skipping...")
                continue
            file_path = file[len("repo/"):]
            file_paths.append(file_path)
            file_contents.append(contents)
            if len(file_list) > MAX_FILES:
                score_factors.append((1, 2, 5)) # This is a low score
                continue
            try:
                cache_key = f"{repo_name}-{file_path}-{CACHE_VERSION}"
                if cache_inst and cache_success:
                    cached_value = cache_inst.get(cache_key)
                    if cached_value:
                        score_factor = json.loads(cached_value)
                        score_factors.append(score_factor)
                        continue
                commits = list(repo.get_commits(path=file_path, sha=branch_name))
                score_factor = get_factors(contents, commits)
                if cache_inst and cache_success:
                    cache_inst.set(cache_key, json.dumps(score_factor), ex=60 * 60 * 2)
                score_factors.append(score_factor)
            except Exception as e:
                logger.warning(f"Received warning during scoring {e}, skipping...")
                score_factors.append((1, 2, 5))
                continue
    scores = get_scores(score_factors) # take percentiles + sum the scores

    logger.info(f"Finished getting list of files, chunking...")
    def chunk_into_sublists(lst, sublist_size=200) -> list[list]:
        return [lst[i:i + sublist_size] for i in range(0, len(lst), sublist_size)]

    file_contents_batches = chunk_into_sublists(file_contents)
    file_paths_batches = chunk_into_sublists(file_paths)
    scores_batches = chunk_into_sublists(scores)

    logger.info(f"Batched into {len(file_contents_batches)} batches...")

    chunked_results = []
    for batch in chunker.starmap(zip(file_contents_batches, file_paths_batches, scores_batches), kwargs={"additional_metadata": {"repo_name": repo_name, "branch_name": branch_name}}):
        chunked_results.extend(batch)

    # Todo(lukejagg): Should we default return ([], [], []) on empty list?
    documents, metadatas, ids = zip(*chunked_results) if len(chunked_results) > 0 else ([], [], [])
    documents = [item for sublist in documents for item in sublist]
    metadatas = [item for sublist in metadatas for item in sublist]
    ids = [item for sublist in ids for item in sublist]

    logger.info(f"Used {len(file_paths)} files...")

    shutil.rmtree("repo", ignore_errors=True)
    logger.info(f"Getting list of all files took {time.time() - start}")
    logger.info(
        f"Received {len(documents)} documents from repository {repo_name}")
    collection_name = parse_collection_name(repo_name)
    return compute_deeplake_vs(collection_name, documents, cache_success, cache_inst, ids, metadatas, commit_hash)


def compute_deeplake_vs(collection_name,
                        documents,
                        cache_success,
                        cache_inst,
                        ids,
                        metadatas,
                        sha):
    deeplake_vs = init_deeplake_vs(collection_name)
    if len(documents) > 0:
        logger.info("Computing embeddings...")
        # Check cache here for all documents
        embeddings = [None] * len(documents)
        if cache_inst and cache_success:
            cache_keys = [hash_sha256(
                doc) + SENTENCE_TRANSFORMERS_MODEL + CACHE_VERSION for doc in documents]
            cache_values = cache_inst.mget(cache_keys)
            for idx, value in enumerate(cache_values):
                if value is not None:
                    embeddings[idx] = json.loads(value)
        logger.info(
            f"Found {len([x for x in embeddings if x is not None])} embeddings in cache")
        indices_to_compute = [idx for idx,
        x in enumerate(embeddings) if x is None]
        documents_to_compute = [documents[idx] for idx in indices_to_compute]

        logger.info(f"Computing {len(documents_to_compute)} embeddings...")
        computed_embeddings = embedding_function(documents_to_compute)
        logger.info(f"Computed {len(computed_embeddings)} embeddings")

        for idx, embedding in zip(indices_to_compute, computed_embeddings):
            embeddings[idx] = embedding
       
        logger.info("Adding embeddings to deeplake vector store...")
        deeplake_vs.add(
            text=ids,
            embedding=embeddings,
            metadata=metadatas
        )
        logger.info("Added embeddings to deeplake vector store")
        if cache_inst and cache_success and len(documents) < 500:
            cache_inst.set(f"github-{sha}{CACHE_VERSION}", json.dumps(
                {"metadatas": metadatas, "ids": ids, "embeddings": embeddings}))
        if cache_inst and cache_success and len(documents_to_compute) > 0:
            logger.info(f"Updating cache with {len(computed_embeddings)} embeddings")
            cache_keys = [hash_sha256(
                doc) + SENTENCE_TRANSFORMERS_MODEL + CACHE_VERSION for doc in documents_to_compute]
            cache_inst.mset({key: json.dumps(value)
                            for key, value in zip(cache_keys, computed_embeddings)})
        logger.info("Finished indexing repository")
        return deeplake_vs
    else:
        logger.error("No documents found in repository")
        return deeplake_vs


@stub.function(image=image, secrets=secrets, network_file_systems={DISKCACHE_DIR: model_volume}, timeout=timeout, keep_warm=2, cpu=CPU)
def update_index(
        repo_name,
        installation_id: int,
        sweep_config: SweepConfig = SweepConfig(),
) -> int:
    get_deeplake_vs_from_repo(repo_name, installation_id, branch_name=None, sweep_config=sweep_config)
    return 0


@stub.function(image=image, secrets=secrets, network_file_systems={DEEPLAKE_DIR: model_volume}, timeout=timeout, keep_warm=1, cpu=CPU)
def get_relevant_snippets(
        repo_name: str,
        query: str,
        n_results: int,
        installation_id: int,
        username: str | None = None,
        sweep_config: SweepConfig = SweepConfig(),
):
    logger.info("Starting search by getting vector store...")
    deeplake_vs = get_deeplake_vs_from_repo(
        repo_name=repo_name, installation_id=installation_id, sweep_config=sweep_config
    )
    logger.info("Searching for relevant snippets...")
    results = {"metadata": [], "text": []}
    for n_result in range(n_results, 0, -1):
        try:
            query_embedding = embedding_function([query], cpu=True)[0]
            results = deeplake_vs.search(embedding=query_embedding, k=n_result)
            break
        except Exception:
            pass
    logger.info("Fetched relevant snippets...")
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
        return []
    metadatas = results["metadata"]
    code_scores = [metadata["score"] for metadata in metadatas]
    vector_scores = results["score"]
    combined_scores = [code_score + vector_score for code_score,
    vector_score in zip(code_scores, vector_scores)]
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