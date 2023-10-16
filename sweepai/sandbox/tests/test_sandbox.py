import sys; sys.path.insert(0, "/repo/sweepai/sandbox/")

if __name__ == "__main__":
    from fastapi.testclient import TestClient
    from sweepai.sandbox.src.chat import app  # Import the FastAPI application

    client = TestClient(app)  # Use the FastAPI application
    data = {
        "repo_url": "https://github.com/sweepai/landing-page",
        "code": "some_code",  # Provide the 'code' argument
        "stdout": "some_stdout",  # Provide the 'stdout' argument
    }
    response = client.post("/", json=data)
    print(response.text)
