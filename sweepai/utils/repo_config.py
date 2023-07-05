import yaml

class RepoConfig:
    def __init__(self):
        self.settings = self.load_settings()

    def load_settings(self):
        with open("sweep.yaml", "r") as file:
            settings = yaml.safe_load(file)
        return settings
