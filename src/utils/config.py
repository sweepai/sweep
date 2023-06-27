import yaml
from github.Repository import Repository
from pydantic import BaseModel

class SweepConfig(BaseModel):
    include_dirs: list[str] = []
    exclude_dirs: list[str] = [".git", "node_modules", "venv"]
    include_exts: list[str] = ['.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs']
    exclude_exts: list[str] = ['.min.js', '.min.js.map', '.min.css', '.min.css.map']
    max_file_limit: int = 60_000
    sweep_branch: str | None = None # defaults to the default github branch
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> "SweepConfig":
        data = yaml.safe_load(yaml_str)
        return cls.parse_obj(data)
    
    @classmethod
    def from_repo(cls, repo: Repository) -> "SweepConfig":
        try:
            contents = repo.get_contents("sweep.yaml")
        except:
            return cls()
        return SweepConfig.from_yaml(contents.decoded_content.decode("utf-8"))
    