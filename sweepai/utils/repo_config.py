import yaml
from github import Github

class RepoConfig:
    def __init__(self, github_repo: Github):
        self.github_repo = github_repo

    def read_sweep_yaml(self):
        try:
            sweep_yaml = self.github_repo.get_contents("sweep.yaml")
            return sweep_yaml.decoded_content
        except Exception as e:
            print(f"Error reading sweep.yaml: {e}")
            return None

    def load_settings(self):
        sweep_yaml_content = self.read_sweep_yaml()
        if sweep_yaml_content is not None:
            settings = yaml.safe_load(sweep_yaml_content)
            return settings
        else:
            return None
