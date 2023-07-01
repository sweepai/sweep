import unittest
from sweepai import vector_db

class TestVectorDB(unittest.TestCase):
    def setUp(self):
        self.vector_db = vector_db.VectorDB()
        self.test_data = ['test1', 'test2', 'test3']
        self.vector_db.add(self.test_data)

    def test_search(self):
        result = self.vector_db.search('test1')
        self.assertEqual(result, ['test1'])

    def test_exception_handling(self):
        with self.assertRaises(Exception):
            self.vector_db.search('nonexistent')
</new_file>

