import unittest

from fastapi.testclient import TestClient

from sweepai.fastapi_endpoint import app


class TestFastAPIEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_read_root(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Hello, Sweep!"})
