import json
import numpy as np
from redis import Redis
from loguru import logger

# Redis client
redis_client = Redis.from_url(REDIS_URL)

def chunk(texts: List[str], batch_size: int) -> Generator[List[str], None, None]:
    texts = [text[:4096] if text else " " for text in texts]
    for text in texts:
        assert isinstance(text, str), f"Expected str, got {type(text)}"
        assert len(text) <= 4096, f"Expected text length <= 4096, got {len(text)}"
    for i in range(0, len(texts), batch_size):
        yield texts[i : i + batch_size] if i + batch_size < len(texts) else texts[i:]

def parse_collection_name(name: str) -> str:
    name = re.sub(r"[^\w-]", "--", name)
    name = re.sub(r"^(-*\w{0,61}\w)-*$", r"\1", name[:63].ljust(3, "x"))
    return name
