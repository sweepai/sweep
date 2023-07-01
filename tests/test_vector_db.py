import unittest
from sweepai import vector_db

class TestVectorDB(unittest.TestCase):
    def setUp(self):
        self.vector_db = vector_db.VectorDB()

    def test_search(self):
        query = "test"
        result = self.vector_db.search(query)
        self.assertIsNotNone(result)

        query = ""
        result = self.vector_db.search(query)
        self.assertIsNone(result)

    def test_search_exception(self):
        with self.assertRaises(Exception):
            self.vector_db.search(None)
</new_file>

