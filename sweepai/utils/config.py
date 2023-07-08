from loguru import logger
import yaml
from github.Repository import Repository
from pydantic import BaseModel

class SweepConfig(BaseModel):
    include_dirs: list[str] = []
    exclude_dirs: list[str] = [".git", "node_modules", "venv"]
    include_exts: list[str] = ['.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs']
    exclude_exts: list[str] = ['.min.js', '.min.js.map', '.min.css', '.min.css.map']
    max_file_limit: int = 60_000
    
    def to_yaml(self) -> str:
        return yaml.safe_dump(self.dict())
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> "SweepConfig":
        data = yaml.safe_load(yaml_str)
        return cls.parse_obj(data)
    
    @staticmethod
    def get_branch(repo: Repository) -> "SweepConfig":
        try:
            contents = repo.get_contents(".github/sweep.yaml")
            branch = yaml.safe_load(contents.decoded_content.decode("utf-8"))["branch"]
            repo.create_branch(branch)
            return branch
        except Exception as e:
            logger.warning(f"Error when getting branch: {e}, falling back to default branch")
            return repo.default_branch