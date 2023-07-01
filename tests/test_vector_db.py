import unittest
from sweep.vector_db import VectorDB

class TestVectorDB(unittest.TestCase):
    def setUp(self):
        self.vector_db = VectorDB()

    def test_search(self):
        # Test search functionality with a known vector
        result = self.vector_db.search('known_vector')
        self.assertIsNotNone(result)

    def test_search_exception(self):
        # Test search functionality with an unknown vector
        with self.assertRaises(Exception):
            self.vector_db.search('unknown_vector')
</new_file>

