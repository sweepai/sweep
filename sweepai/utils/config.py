from functools import lru_cache
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
    label_only: bool = False
    
    def to_yaml(self) -> str:
        return yaml.safe_dump(self.dict())
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> "SweepConfig":
        data = yaml.safe_load(yaml_str)
        return cls.parse_obj(data)

    @staticmethod
    @lru_cache(maxsize=None)
    def get_branch(repo: Repository) -> str:
        default_branch = repo.default_branch
        try:
            contents = repo.get_contents(".github/sweep.yaml")
            branch_name = yaml.safe_load(contents.decoded_content.decode("utf-8"))["branch"]
            try:
                repo.get_branch(branch_name)
                return branch_name
            except Exception as e:
                logger.warning(f"Error when getting branch: {e}, creating branch")
                repo.create_git_ref(f"refs/heads/{branch_name}", repo.get_branch(default_branch).commit.sha)
                return branch_name
        except Exception as e:
            logger.warning(f"Error when getting branch: {e}, falling back to default branch")
            return default_branch