import unittest
from tests.example_code.chroma_fastapi import FastAPI

class TestFastAPI(unittest.TestCase):
    def test_raw_sql_multiple_queries(self):
        # Create a FastAPI instance
        fastapi = FastAPI()

        # Define a list of SQL queries
        queries = ["SELECT * FROM table1", "SELECT * FROM table2"]

        # Call the raw_sql method with the list of queries
        results = fastapi.raw_sql(queries)

        # Assert that the method returns a list of dataframes
        self.assertIsInstance(results, list)
        for result in results:
            self.assertIsInstance(result, pd.DataFrame)


