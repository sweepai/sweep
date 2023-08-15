import modal
from pydantic import BaseModel
from fastapi import FastAPI

from sweepai.config.server import ENV


stub = modal.Stub(ENV + "-ext")
image = (
    modal.Image.debian_slim()
    .pip_install(
    )
)
secrets = [
    modal.Secret.from_name("github"),
]

FUNCTION_SETTINGS = {
    "image": image,
    "secrets": secrets,
    "timeout": 60 * 60,
    "keep_warm": 1,
}

@stub.function(**FUNCTION_SETTINGS)
@modal.asgi_app(label=ENV+"-ext")
def _asgi_app():
    asgi_app = FastAPI()

    class Config(BaseModel):
        username: str
        pat: str

    class CheckRepoRequest(BaseModel):
        repo_full_name: str
        config: Config

    @asgi_app.post("/check_repo")
    def check_repo(request: CheckRepoRequest):
        pass

    class CreateIssueRequest(BaseModel):
        repo_full_name: str
        title: str
        body: str
        username: str
        config: Config

    @asgi_app.post("/create_issue")
    def create_issue(request: CreateIssueRequest):
        pass
    
    return asgi_app
