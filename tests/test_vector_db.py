import unittest
from sweep.vector_db import retrieve_code

class TestVectorDB(unittest.TestCase):
    def setUp(self):
        self.query_success = "valid query"
        self.query_fail = "invalid query"

    def test_retrieve_code_success(self):
        result = retrieve_code(self.query_success)
        self.assertIsNotNone(result)

    def test_retrieve_code_fail(self):
        with self.assertRaises(Exception):
            retrieve_code(self.query_fail)

if __name__ == "__main__":
    unittest.main()

