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

from src.core.entities import Snippet
from src.utils.event_logger import posthog
from src.utils.hash import hash_sha256

from ..utils.github_utils import get_token
from ..utils.constants import DB_NAME, BOT_TOKEN_NAME, ENV
from ..utils.config import SweepConfig
import time

# TODO: Lots of cleanups can be done here with these constants
stub = modal.Stub(DB_NAME)
chunker = modal.Function.lookup("utils", "Chunking.chunk")
model_volume = modal.SharedVolume().persist(f"{ENV}-storage")
MODEL_DIR = "/root/cache/model"
DEEPLAKE_DIR = "/root/cache/"
DISKCACHE_DIR = "/root/cache/diskcache/"
DEEPLAKE_FOLDER = "deeplake/"
BATCH_SIZE = 256
SENTENCE_TRANSFORMERS_MODEL = "sentence-transformers/all-MiniLM-L12-v2"
timeout = 60 * 30 # 30 minutes

image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install("deeplake==3.6.3", "sentence-transformers")
    .pip_install("openai", "PyGithub", "loguru", "docarray", "GitPython", "tqdm", "highlight-io", "anthropic", "posthog", "redis")
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

def list_collection_names():
    """Returns a list of all collection names."""
    collections = []
    return collections

@stub.cls(
    image=image,
    secrets=secrets,
    shared_volumes={MODEL_DIR: model_volume},
    keep_warm=1,
    gpu="T4",
    retries=modal.Retries(max_retries=5, backoff_coefficient=2, initial_delay=5),
)
class Embedding:
    def __enter__(self):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
        )

    @method()
    def compute(self, texts: list[str]):
        return self.model.encode(texts, batch_size=BATCH_SIZE).tolist()

    @method()
    def ping(self):
        return "pong"

class ModalEmbeddingFunction():
    def __init__(self):
        pass

    def __call__(self, texts):
        return Embedding.compute.call(texts)

embedding_function = ModalEmbeddingFunction()

def get_deeplake_vs_from_repo(
    repo_name: str,
    sweep_config: SweepConfig = SweepConfig(),
    installation_id: int = None,
    branch_name: str = None,
):
    logger.info(f"Downloading repository and indexing for {repo_name}...")
    token = get_token(installation_id)
    g = Github(token)
    repo = g.get_repo(repo_name)
    try:
        labels = repo.get_labels()
        label_names = [label.name for label in labels]

        if "sweep" not in label_names:
            repo.create_label(
                name="sweep",
                color="5319E7",
                description="Assigns Sweep to an issue or pull request.",
            )
    except Exception as e:
        logger.error(f"Received error {e}")
        logger.warning("Repository already exists, skipping initialization")

    start = time.time()
    logger.info("Recursively getting list of files...")

    repo_url = f"https://x-access-token:{token}@github.com/{repo_name}.git"
    shutil.rmtree("repo", ignore_errors=True)
    Repo.clone_from(repo_url, "repo")

    file_list = glob.iglob("repo/**", recursive=True)
    file_list = [
        file
        for file in tqdm(file_list)
        if os.path.isfile(file)
        and all(not file.endswith(ext) for ext in sweep_config.exclude_exts)
        and all(not file[len("repo/"):].startswith(dir_name) for dir_name in sweep_config.exclude_dirs)
    ]

    branch_name = repo.default_branch

    file_paths = []
    file_contents = []

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
            except UnicodeDecodeError as e:
                logger.warning(f"Received warning {e}, skipping...")
                continue
            file_path = file[len("repo/") :]
            file_paths.append(file_path)
            file_contents.append(contents)
        
    chunked_results = chunker.map(file_contents, file_paths, kwargs={
        "additional_metadata": {"repo_name": repo_name, "branch_name": branch_name}
    })

    documents, metadatas, ids = zip(*chunked_results)
    documents = [item for sublist in documents for item in sublist]
    metadatas = [item for sublist in metadatas for item in sublist]
    ids = [item for sublist in ids for item in sublist]
    
    logger.info(f"Used {len(file_paths)} files...")

    shutil.rmtree("repo")
    logger.info(f"Getting list of all files took {time.time() -start}")
    logger.info(f"Received {len(documents)} documents from repository {repo_name}")
    collection_name = parse_collection_name(repo_name)

    deeplake_vs = init_deeplake_vs(collection_name)
    if len(documents) > 0:
        logger.info("Computing embeddings...")
        # Check cache here for all documents
        embeddings = [None] * len(documents)
        cache_success = True
        try:
            cache = Redis.from_url(os.environ.get("redis_url"))
            logger.info(f"Succesfully got cache for {collection_name}")
        except:
            cache_success = False
        if cache_success:
            cache_keys = [hash_sha256(doc) + SENTENCE_TRANSFORMERS_MODEL for doc in documents]
            cache_values = cache.mget(cache_keys)
            for idx, value in enumerate(cache_values):
                if value is not None:
                    embeddings[idx] = json.loads(value)
        logger.info(f"Found {len([x for x in embeddings if x is not None])} embeddings in cache")
        indices_to_compute = [idx for idx, x in enumerate(embeddings) if x is None]
        documents_to_compute = [documents[idx] for idx in indices_to_compute]

        computed_embeddings = embedding_function(documents_to_compute)

        for idx, embedding in zip(indices_to_compute, computed_embeddings):
            embeddings[idx] = embedding
        deeplake_vs.add(
            text = ids,
            embedding = embeddings,
            metadata = metadatas
        )
        if cache_success and len(documents_to_compute) > 0:
            logger.info(f"Updating cache with {len(computed_embeddings)} embeddings")
            cache_keys = [hash_sha256(doc) + SENTENCE_TRANSFORMERS_MODEL for doc in documents_to_compute]
            cache.mset({key: json.dumps(value) for key, value in zip(cache_keys, computed_embeddings)})
        return deeplake_vs
    else:
        logger.error("No documents found in repository")
        return deeplake_vs

@stub.function(image=image, secrets=secrets, shared_volumes={DISKCACHE_DIR: model_volume}, timeout=timeout)
def init_index(
    repo_name: str,
    installation_id: int,
    sweep_config: SweepConfig = SweepConfig(),
):
    pass


@stub.function(image=image, secrets=secrets, shared_volumes={DISKCACHE_DIR: model_volume}, timeout=timeout)
def update_index(
    repo_name,
    installation_id: int,
    sweep_config: SweepConfig = SweepConfig(),
) -> int:
    pass


@stub.function(image=image, secrets=secrets, shared_volumes={DEEPLAKE_DIR: model_volume}, timeout=timeout)
def get_relevant_snippets(
    repo_name: str,
    query: str,
    n_results: int,
    installation_id: int,
    username: str = None,
    sweep_config: SweepConfig = SweepConfig(),
):
    collection_names = list_collection_names()
    logger.info("DeepLake collections: {}".format(collection_names))
    collection_name = parse_collection_name(repo_name)
    if collection_name not in collection_names:
        init_index(
            repo_name=repo_name,
            installation_id=installation_id,
            sweep_config=sweep_config,
        )
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
    relevant_paths = [metadata["file_path"] for metadata in metadatas]
    logger.info("Relevant paths: {}".format(relevant_paths))
    return [
        Snippet(
            content="",
            start=metadata["start"], 
            end=metadata["end"], 
            file_path=file_path
        ) for metadata, file_path in zip(metadatas, relevant_paths)
    ]
