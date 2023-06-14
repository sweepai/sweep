import requests  # type: ignore
from pydantic import BaseModel


class JinaClient(BaseModel):
    url: str

    def __init__(self, url: str):
        super().__init__(url=url)

    def search(self, query: str):
        payload = {"data": [{"text": query}], "parameters": {}}
        response = requests.post(f"{self.url}/search", json=payload)
        return response.json()
