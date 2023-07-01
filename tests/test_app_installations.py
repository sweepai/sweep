import os
import requests

from sweepai.utils.github_utils import get_jwt


username = "sweepai"
os.environ["GITHUB_APP_PEM"] = """
-----BEGIN RSA PRIVATE KEY-----
xxxxxxxxx
-----END RSA PRIVATE KEY-----
"""
jwt = get_jwt()
print(f"https://api.github.com/orgs/{username}/installation")
response = requests.get(
    f"https://api.github.com/orgs/{username}/installation",
    headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + jwt,
        "X-GitHub-Api-Version": "2022-11-28",
    },
)
print(response.json()["id"])
