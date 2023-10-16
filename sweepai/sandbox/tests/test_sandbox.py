import sys; sys.path.insert(0, "/repo/sweepai/sandbox/")

if __name__ == "__main__":
    from fastapi.testclient import TestClient
    from sweepai.sandbox.src.chat import fix_file

    client = TestClient(fix_file)
    data = {
        "repo_url": "https://github.com/sweepai/landing-page",
    }
    response = client.post("/", json=data)
    print(response.text)
