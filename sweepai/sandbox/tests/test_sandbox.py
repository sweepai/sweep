if __name__ == "__main__":
    from fastapi.testclient import TestClient
    from .sandbox_local import app

    client = TestClient(app)
    data = {
        "repo_url": "https://github.com/sweepai/landing-page",
        "file_path": "path/to/file",
        "content": "file contents",
    }
    response = client.post("/", json=data)
    print(response.text)
