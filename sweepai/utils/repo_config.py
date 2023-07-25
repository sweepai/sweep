from github import Repository
import yaml

class RepoConfig:
    def __init__(self, repo: Repository):
        self.repo = repo
        self.config = None
        self.load_config()

    def load_config(self):
        try:
            config_file = self.repo.get_contents("sweep.yaml")
            self.config = yaml.safe_load(config_file.decoded_content)
        except Exception as e:
            print(f"Error loading config: {e}")
