import re

from sweepai.utils.diff import sliding_window_replacement

updated_pattern = r"<<<<<<<\s+REPLACE\s+\(index=(?P<index>\d+)\)(?P<original_code>.*?)=======(?P<updated_code>.*?)>>>>>>>"
append_pattern = (
    r"<<<<<<<\s+APPEND\s+\(index=(?P<index>\d+)\)(?P<updated_code>.*?)>>>>>>>"
)

old_file = """
def embed_huggingface(texts):
    for i in range(3):
        try:
            headers = {
                "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
                "Content-Type": "application/json",
            }
            response = requests.post(
                HUGGINGFACE_URL, headers=headers, json={"inputs": texts}
            )
            return response.json()["embeddings"]
        except requests.exceptions.RequestException as e:
            logger.exception(
                f"Error occurred when sending request to Hugging Face endpoint: {e}"
            )


def embed_replicate(texts: List[str]) -> List[np.ndarray]:
    client = replicate.Client(api_token=REPLICATE_API_KEY)
    deployment = client.deployments.get(REPLICATE_DEPLOYMENT_URL)
    e = None
    for i in range(3):
        try:
            prediction = deployment.predictions.create(
                input={"text_batch": json.dumps(texts)}, timeout=60
            )
            prediction.wait()
            outputs = prediction.output
            break
        except Exception:
            logger.exception(f"Replicate timeout: {e}")
    else:
        raise Exception(f"Replicate timeout")
    return [output["embedding"] for output in outputs]


@lru_cache(maxsize=64)
def embed_texts(texts: tuple[str]):
    logger.info(
        f"Computing embeddings for {len(texts)} texts using {VECTOR_EMBEDDING_SOURCE}..."
    )
    match VECTOR_EMBEDDING_SOURCE:
        case "sentence-transformers":
            sentence_transformer_model = SentenceTransformer(
                SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
            )
            vector = sentence_transformer_model.encode(
                texts, show_progress_bar=True, batch_size=BATCH_SIZE
            )
            return vector
        case "openai":
            import openai

            embeddings = []
            for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE), disable=False):
                try:
                    response = openai.Embedding.create(
                        input=batch, model="text-embedding-ada-002"
                    )
                    embeddings.extend([r["embedding"] for r in response["data"]])
                except SystemExit:
                    raise SystemExit
                except Exception:
                    logger.exception("Failed to get embeddings for batch")
                    logger.error(f"Failed to get embeddings for {batch}")
            return embeddings
        case "huggingface":
            if HUGGINGFACE_URL and HUGGINGFACE_TOKEN:
                embeddings = []
                for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE), disable=False):
                    embeddings.extend(embed_huggingface(texts))
                return embeddings
            else:
                raise Exception("Hugging Face URL and token not set")
        case "replicate":
            if REPLICATE_API_KEY:
                embeddings = []
                for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE)):
                    embeddings.extend(embed_replicate(batch))
                return embeddings
            else:
                raise Exception("Replicate URL and token not set")
        case _:
            raise Exception("Invalid vector embedding mode")
    logger.info(
        f"Computed embeddings for {len(texts)} texts using {VECTOR_EMBEDDING_SOURCE}"
    )
"""

update_snippets_response = """
<diffs>
```\n<<<<<<< REPLACE (index=1)
def embed_huggingface(texts):
    for i in range(3):
        try:
            headers = {
                "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
                "Content-Type": "application/json",
            }
            response = requests.post(
                HUGGINGFACE_URL, headers=headers, json={"inputs": texts}
            )
            return response.json()["embeddings"]
        except requests.exceptions.RequestException as e:
            logger.exception(
                f"Error occurred when sending request to Hugging Face endpoint: {e}"
            )


def embed_replicate(texts: List[str]) -> List[np.ndarray]:
    client = replicate.Client(api_token=REPLICATE_API_KEY)
    deployment = client.deployments.get(REPLICATE_DEPLOYMENT_URL)
    e = None
    for i in range(3):
        try:
            prediction = deployment.predictions.create(
                input={"text_batch": json.dumps(texts)}, timeout=60
            )
            prediction.wait()
            outputs = prediction.output
            break
        except Exception:
            logger.exception(f"Replicate timeout: {e}")
    else:
        raise Exception(f"Replicate timeout")
    return [output["embedding"] for output in outputs]
=======
def embed_huggingface(texts):
    headers = {
        "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        HUGGINGFACE_URL, headers=headers, json={"inputs": texts}
    )
    return response.json()["embeddings"]


def embed_replicate(texts: List[str]) -> List[np.ndarray]:
    client = replicate.Client(api_token=REPLICATE_API_KEY)
    deployment = client.deployments.get(REPLICATE_DEPLOYMENT_URL)
    prediction = deployment.predictions.create(
        input={"text_batch": json.dumps(texts)}, timeout=60
    )
    prediction.wait()
    outputs = prediction.output
    return [output["embedding"] for output in outputs]
>>>>>>>

<<<<<<< APPEND (index=1)
def compute_embeddings(texts: List[str], batch_size: int, embed_func):
    embeddings = []
    for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE), disable=False):
        try:
            embeddings.extend(embed_func(batch))
        except SystemExit:
            raise SystemExit
        except Exception:
            logger.exception("Failed to get embeddings for batch")
            logger.error(f"Failed to get embeddings for {batch}")
    return embeddings
>>>>>>>
\n<<<<<<< REPLACE (index=1)
@lru_cache(maxsize=64)
def embed_texts(texts: tuple[str]):
    logger.info(
        f"Computing embeddings for {len(texts)} texts using {VECTOR_EMBEDDING_SOURCE}..."
    )
    match VECTOR_EMBEDDING_SOURCE:
        case "sentence-transformers":
            sentence_transformer_model = SentenceTransformer(
                SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
            )
            vector = sentence_transformer_model.encode(
                texts, show_progress_bar=True, batch_size=BATCH_SIZE
            )
            return vector
        case "openai":
            import openai

            embeddings = []
            for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE), disable=False):
                try:
                    response = openai.Embedding.create(
                        input=batch, model="text-embedding-ada-002"
                    )
                    embeddings.extend([r["embedding"] for r in response["data"]])
                except SystemExit:
                    raise SystemExit
                except Exception:
                    logger.exception("Failed to get embeddings for batch")
                    logger.error(f"Failed to get embeddings for {batch}")
            return embeddings
        case "huggingface":
            if HUGGINGFACE_URL and HUGGINGFACE_TOKEN:
                embeddings = []
                for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE), disable=False):
                    embeddings.extend(embed_huggingface(texts))
                return embeddings
            else:
                raise Exception("Hugging Face URL and token not set")
        case "replicate":
            if REPLICATE_API_KEY:
                embeddings = []
                for batch in tqdm(chunk(texts, batch_size=BATCH_SIZE)):
                    embeddings.extend(embed_replicate(batch))
                return embeddings
            else:
                raise Exception("Replicate URL and token not set")
        case _:
            raise Exception("Invalid vector embedding mode")
    logger.info(
        f"Computed embeddings for {len(texts)} texts using {VECTOR_EMBEDDING_SOURCE}"
    )
=======
@lru_cache(maxsize=64)
def embed_texts(texts: tuple[str]):
    logger.info(
        f"Computing embeddings for {len(texts)} texts using {VECTOR_EMBEDDING_SOURCE}..."
    )
    match VECTOR_EMBEDDING_SOURCE:
        case "sentence-transformers":
            sentence_transformer_model = SentenceTransformer(
                SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR
            )
            return sentence_transformer_model.encode(
                texts, show_progress_bar=True, batch_size=BATCH_SIZE
            )
        case "openai":
            import openai
            return compute_embeddings(texts, BATCH_SIZE, openai.Embedding.create)
        case "huggingface":
            if HUGGINGFACE_URL and HUGGINGFACE_TOKEN:
                return compute_embeddings(texts, BATCH_SIZE, embed_huggingface)
            else:
                raise Exception("Hugging Face URL and token not set")
        case "replicate":
            if REPLICATE_API_KEY:
                return compute_embeddings(texts, BATCH_SIZE, embed_replicate)
            else:
                raise Exception("Replicate URL and token not set")
        case _:
            raise Exception("Invalid vector embedding mode")
    logger.info(
        f"Computed embeddings for {len(texts)} texts using {VECTOR_EMBEDDING_SOURCE}"
    )
>>>>>>>
```
</diffs>
"""

selected_snippets = {1: ("", old_file)}
updated_snippets = {}

for match_ in re.finditer(updated_pattern, update_snippets_response, re.DOTALL):
    index = int(match_.group("index"))
    original_code = match_.group("original_code").strip("\n")
    updated_code = match_.group("updated_code").strip("\n")

    _reason, current_contents = selected_snippets[index]
    if index not in updated_snippets:
        updated_snippets[index] = current_contents
    else:
        current_contents = updated_snippets[index]
    updated_snippets[index] = "\n".join(
        sliding_window_replacement(
            original=current_contents.splitlines(),
            search=original_code.splitlines(),
            replace=updated_code.splitlines(),
        )[0]
    )

for match_ in re.finditer(append_pattern, update_snippets_response, re.DOTALL):
    index = int(match_.group("index"))
    updated_code = match_.group("updated_code").strip("\n")

    _reason, current_contents = selected_snippets[index]
    if index not in updated_snippets:
        updated_snippets[index] = current_contents
    else:
        current_contents = updated_snippets[index]
    updated_snippets[index] = current_contents + "\n" + updated_code
