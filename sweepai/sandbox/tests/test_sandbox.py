if __name__ == "__main__":
    from fastapi.testclient import TestClient
    from src.sandbox_local import app

    client = TestClient(app)
    data = {
        "repo_url": "https://github.com/sweepai/landing-page",
        # "file_path": file_path,
        # "content": bad_file_contents,
    }
    response = client.post("/", json=data)
    print(response.text)
