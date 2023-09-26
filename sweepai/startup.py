SENTENCE_TRANSFORMERS_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_DIR = "/tmp/cache/model"


def download_models():
    from sentence_transformers import (
        SentenceTransformer,
    )  # pylint: disable=import-error

    model = SentenceTransformer(SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR)


download_models()
import subprocess

subprocess.run(["playwright", "install"])
