import os
import requests
from chromadb.utils import embedding_functions

HUGGINGFACE_INFERENCE_URL = "https://r0gyxxwg0w192f22.us-east-1.aws.endpoints.huggingface.cloud"


class HuggingfaceEndpointEmbeddingFunction(embedding_functions.EmbeddingFunction):
    def __init__(self, token: str = os.environ.get("HUGGINGFACE_TOKEN", None)):
        self._token = token
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

    def __call__(self, texts):
        # Call HuggingFace Embedding API for each document
        assert self._token
        response = self._session.post(
            HUGGINGFACE_INFERENCE_URL, 
            json={'inputs': texts}
        )
        json = response.json()
        embeddings = json["embeddings"]
        return embeddings

