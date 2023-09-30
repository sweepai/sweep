import os

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

load_dotenv(dotenv_path=".env")

app = FastAPI()

DEV_URL = os.environ.get("DEV_URL", "http://127.0.0.1:8080")
BACKUP_URL = os.environ.get("BACKUP_DEV_URL", "http://127.0.0.1:8080")
HEALTH_ENDPOINT = "/health"

assert DEV_URL is not None, "DEV_URL must be set"
assert BACKUP_URL is not None, "BACKUP_DEV_URL must be set"

print(f"DEV_URL: {DEV_URL}")
print(f"BACKUP_DEV_URL: {BACKUP_URL}")


def is_dev_up():
    response = requests.get(f"{DEV_URL}{HEALTH_ENDPOINT}")
    return response.status_code == 200


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def forward_request(path: str, request: Request):
    target_url = DEV_URL if is_dev_up() else BACKUP_URL
    print(f"Forwarding request to {target_url}/{path}")
    return RedirectResponse(url=f"{target_url}/{path}")
