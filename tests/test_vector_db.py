import unittest
from src.core.vector_db import compute_deeplake_vs
from src.core.vector_db import DeepLakeVectorStore

class TestVectorDB(unittest.TestCase):
    def test_compute_deeplake_vs(self):
        # Sample data
        collection_name = "test_collection"
        documents = ["Represent this code snippet for retrieval:\n" + "print('Hello, world!')"]
        cache_success = False
        cache = None
        ids = ["test_id"]
        metadatas = [{"score": 1.0}]
        sha = "test_sha"

        # Call the function with the sample data
        deeplake_vs = compute_deeplake_vs(collection_name, documents, cache_success, cache, ids, metadatas, sha)

        # Check that the function returned a DeepLakeVectorStore object
        self.assertIsInstance(deeplake_vs, DeepLakeVectorStore)

        # Check that the object contains the correct data
        self.assertEqual(deeplake_vs.text, ids)
        self.assertEqual(deeplake_vs.metadata, metadatas)
        # The embeddings are hard to check exactly, but we can at least check that they have the right shape
        self.assertEqual(len(deeplake_vs.embedding), len(documents))
        self.assertEqual(len(deeplake_vs.embedding[0]), 768)  # The model we're using produces embeddings of length 768

if __name__ == "__main__":
    unittest.main()

