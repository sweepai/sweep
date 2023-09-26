import requests
from loguru import logger

# Define a list of texts for testing
texts = ["This is a test text.", "Another test text."]


def embed_huggingface(texts):
    """Embeds a list of texts using Hugging Face's API."""
    try:
        headers = {
            "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
            "Content-Type": "application/json",
        }
        imports = {"inputs": texts}
        response = requests.post(
            HUGGINGFACE_URL, headers=headers, json={"inputs": texts}
        )
        response.raise_for_status()
        return response.json()["embeddings"]
    except requests.exceptions.RequestException as e:
        logger.error(
            f"Error occurred when sending request to Hugging Face endpoint: {e}"
        )
