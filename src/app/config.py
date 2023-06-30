from pydantic import BaseModel

CONFIG_FILE = "sweep.yaml"

class Config(BaseModel):
    github_username: str
    github_pat: str # secret
    latest_repo: str | None = None
