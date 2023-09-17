import json
import requests
import time

host = "http://0.0.0.0:8080"
# port = "http://127.0.0.1:8080"

for i in range(120):
    try:
        response = requests.get(host)
        if response.status_code == 200:
            break
    except:
        print(
            f"Waited for server to start ({i+1}s)"
            + ("." * (i % 4) + " " * (4 - (i % 4))),
            end="\r",
        )
        time.sleep(1)
        continue
if i > 0:
    print(f"Waited for server to start ({i+1}s)")

response = requests.post(
    host,
    json=json.load(open("tests/issue_armbian_webhook.json", "r")),
    headers={"X-GitHub-Event": "issues"},
)
print(response)
