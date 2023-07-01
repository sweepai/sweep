import pytest
import time
from src.core.vector_db import compute_deeplake_vs

def test_parallelized_embedding_generation_correctness():
    # Prepare some dummy documents
    documents = ["document1", "document2", "document3"]

    # Compute embeddings using the non-parallelized version
    non_parallel_embeddings = compute_deeplake_vs("collection_name", documents, False, None, ["id1", "id2", "id3"], ["metadata1", "metadata2", "metadata3"], "sha")

    # Compute embeddings using the parallelized version
    parallel_embeddings = compute_deeplake_vs("collection_name", documents, False, None, ["id1", "id2", "id3"], ["metadata1", "metadata2", "metadata3"], "sha")

    # Check if the results are the same
    assert non_parallel_embeddings == parallel_embeddings

def test_parallelized_embedding_generation_performance():
    # Prepare some dummy documents
    documents = ["document1", "document2", "document3"] * 1000

    # Time the execution of the non-parallelized version
    start_time = time.time()
    non_parallel_embeddings = compute_deeplake_vs("collection_name", documents, False, None, ["id1", "id2", "id3"] * 1000, ["metadata1", "metadata2", "metadata3"] * 1000, "sha")
    non_parallel_time = time.time() - start_time

    # Time the execution of the parallelized version
    start_time = time.time()
    parallel_embeddings = compute_deeplake_vs("collection_name", documents, False, None, ["id1", "id2", "id3"] * 1000, ["metadata1", "metadata2", "metadata3"] * 1000, "sha")
    parallel_time = time.time() - start_time

    # Check if the parallelized version is faster
    assert parallel_time < non_parallel_time

