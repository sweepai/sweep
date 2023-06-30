import unittest
from tests.example_code import chroma_fastapi

class TestMultipleQueries(unittest.TestCase):
    def test_get_multiple_queries(self):
        # Create a list of queries
        queries = [
            {"collection_id": "123", "ids": ["1", "2", "3"]},
            {"collection_id": "456", "ids": ["4", "5", "6"]}
        ]

        # Call the _get method with the list of queries
        results = chroma_fastapi._get(queries)

        # Assert that the result is as expected
        self.assertEqual(len(results), len(queries))

    def test_raw_sql_multiple_queries(self):
        # Create a list of SQL queries
        sql_queries = [
            "SELECT * FROM table1",
            "SELECT * FROM table2"
        ]

        # Call the raw_sql method with the list of SQL queries
        results = chroma_fastapi.raw_sql(sql_queries)

        # Assert that the result is as expected
        self.assertEqual(len(results), len(sql_queries))

if __name__ == "__main__":
    unittest.main()
