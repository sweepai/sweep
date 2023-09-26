SENTENCE_TRANSFORMERS_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_DIR = "/tmp/cache/model"


def download_models():
    from sentence_transformers import (  # pylint: disable=import-error
        SentenceTransformer,
    )

    model = SentenceTransformer(SENTENCE_TRANSFORMERS_MODEL, cache_folder=MODEL_DIR)


download_models()
import subprocess

subprocess.run(["playwright", "install"])
