from deeplake.core.vectorstore.deeplake_vectorstore import DeepLakeVectorStore
from loguru import logger
import modal

from src.core.entities import Snippet
from src.utils.config import SweepConfig
from src.utils.constants import DB_NAME
get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")
# get_relevant_snippets.spawn(
#     repo_name="sweepai/bot-internal",
#     installation_id=36855882,
#     query = "Sweep: Add eyes reaction on comment replies",
#     n_results = 10,
#     )
import time
s = time.time()
res = get_relevant_snippets.call(
    repo_name="sweepai/sweep",
    installation_id=36855882,
    query = "Sweep: allow vector db to take multiple queries",
    n_results = 30,
    )
print(res)
e = time.time()
print("Time taken: {}".format(e - s))
import pdb; pdb.set_trace()
# path = "tests/data/test_vectorstore"
# # path = "mem://tests/data/test_vectorstore"

# deeplake_vector_store = DeepLakeVectorStore(
#        path = path,
#        overwrite = True
# )

# list_of_embeddings = [[1, 1, 1,], [-1, -1, -1], [0.5, 0.5, 0.5]]
# metadata = ["hello.py", "world.py", "test.py"]

# deeplake_vector_store.add(
#     text = metadata,
#     embedding = list_of_embeddings,
#     metadata = metadata
# )

# data = deeplake_vector_store.search(
#        embedding = [1, 1, 1],
# )
# deeplake_vector_store_b = DeepLakeVectorStore(
#        path = path,
#        overwrite = False
# )
# data_b = deeplake_vector_store_b.search(
#        embedding = [1, 1, 1],
# )
# import pdb; pdb.set_trace()
# assert data == data_b

# path_c = "tests/data/test_separate--vectorstore"

# deeplake_vector_store_c = DeepLakeVectorStore(
#        path = path_c,
#        overwrite = True
# )
# deeplake_vector_store_c.add(
#     text = metadata,
#     embedding = list_of_embeddings,
#     metadata = metadata
# )

# path_d = "tests/data/test_complex--vectorstore"
# deeplake_vector_store_d = DeepLakeVectorStore(
#        path = path_d,
#        overwrite = True
# )
# metadata_d = [{"file_path": "hello.py", "start": 0, "end": 1}, {"file_path": "world.py", "start": 0, "end": 1}, {"file_path": "test.py", "start": 0, "end": 1}]
# ids_d = ["hello.py:0:1", "world.py:0:1", "test.py:0:1"]
# deeplake_vector_store_d.add(
#     text = ids_d,
#     embedding = list_of_embeddings,
#     metadata = metadata_d
# )
# results = deeplake_vector_store_d.search(
#        embedding = [1, 1, 1],
# )
# metadatas = results["metadata"]
# relevant_paths = [metadata["file_path"] for metadata in metadatas]
# logger.info("Relevant paths: {}".format(relevant_paths))
# snippets = [
#     Snippet(
#         content="",
#         start=metadata["start"], 
#         end=metadata["end"], 
#         file_path=file_path
#     ) for metadata, file_path in zip(metadatas, relevant_paths)
# ]

# # Test opening an existing vectorstore
# path_e = "tests/data/test_complex--vectorstore"
# deeplake_vector_store_e = DeepLakeVectorStore(
#        path = path_e,
#        overwrite = True
# )
# metadata_d = [{"file_path": "hello.py", "start": 0, "end": 1}, {"file_path": "world.py", "start": 0, "end": 1}, {"file_path": "test.py", "start": 0, "end": 1}]
# ids_d = ["hello.py:0:1", "world.py:0:1", "test.py:0:1"]
# deeplake_vector_store_e.add(
#     text = ids_d,
#     embedding = list_of_embeddings,
#     metadata = metadata_d
# )
# results = deeplake_vector_store_e.search(
#        embedding = [1, 1, 1],
# )
# # import pdb; pdb.set_trace()
# # test concurrency
