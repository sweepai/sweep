import requests
from chromadb.utils import embedding_functions

from sweepai.utils.config import HUGGINGFACE_API_KEY, HUGGINGFACE_INFERENCE_URL

if HUGGINGFACE_INFERENCE_URL is not None:
    ENDPOINT = HUGGINGFACE_INFERENCE_URL
else:
    ENDPOINT = "https://r0gyxxwg0w192f22.us-east-1.aws.endpoints.huggingface.cloud"


class HuggingfaceEndpointEmbeddingFunction(embedding_functions.EmbeddingFunction):
    def __init__(self, token: str = HUGGINGFACE_API_KEY):
        self._token = token
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

    def __call__(self, texts):
        # Call HuggingFace Embedding API for each document
        assert self._token
        response = self._session.post(
            ENDPOINT,
            json={'inputs': texts}
        )
        json = response.json()
        embeddings = json["embeddings"]
        return embeddings
