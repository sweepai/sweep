import yaml

class RepoConfig:
    def __init__(self, repo):
        self.repo = repo
        self.load_settings()

    def load_settings(self):
        # Read the sweep.yaml file and load the settings
        with open("sweep.yaml", "r") as file:
            settings = yaml.safe_load(file)
            # Load the settings into the class
            # Rest of code...
