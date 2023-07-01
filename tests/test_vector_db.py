import modal

if __name__ == "__main__":
    app = "dev-db"
    repo = "sweepai/forked_langchain"
    # init_index = modal.Function.lookup(app, "init_index")
    # init_index.call(repo, ["src"], [], [".py"], [], 36855882)

    get_relevant_file_paths = modal.Function.lookup(app, "get_relevant_file_paths")
    print(get_relevant_file_paths.call(repo, "Idea: A memory similar to ConversationBufferWindowMemory but utilizing token length #1598", 5))

import unittest
from src.core.vector_db import Embedding, compute_deeplake_vs

class TestVectorDB(unittest.TestCase):
    def test_compute(self):
        embedding = Embedding()
        texts = ["hello", "world"]
        result = embedding.compute(texts)
        self.assertEqual(len(result), len(texts))
        self.assertTrue(all(isinstance(r, list) for r in result))

    def test_compute_deeplake_vs(self):
        documents = ["document1", "document2"]
        cache_success = True
        cache = {}
        ids = ["id1", "id2"]
        metadatas = [{"metadata1": "value1"}, {"metadata2": "value2"}]
        sha = "123456"
        result = compute_deeplake_vs("collection_name", documents, cache_success, cache, ids, metadatas, sha)
        self.assertIsNotNone(result)

if __name__ == "__main__":
    unittest.main()

