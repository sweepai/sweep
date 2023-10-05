from fastapi.testclient import TestClient
from src.sandbox_local import app
from test_data import bad_file_contents, file_path

client = TestClient(app)

if __name__ == "__main__":
    # headers = {"accept": "application/json", "Content-Type": "application/json"}
    data = {
        "repo_url": "https://github.com/sweepai/landing-page",
        "file_path": file_path,
        "content": bad_file_contents,
    }
    response = client.post("/", json=data)
    print(response.text)
