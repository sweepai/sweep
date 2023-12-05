if __name__ == "__main__":
    import requests
    from test_data import bad_file_contents, file_path

    url = "http://0.0.0.0:8081"
    headers = {"accept": "application/json", "Content-Type": "application/json"}
    data = {
        "repo_url": "https://github.com/sweepai/sweep",
        "file_path": file_path,
        "content": bad_file_contents,
        "check": ["echo 'hello world'"],
    }
    response = requests.post(url, json=data, timeout=(5, 600))
    print(response.text)
