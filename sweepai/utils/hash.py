import hashlib


def hash_sha256(text: str):
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()
