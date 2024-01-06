import yaml

class RepoConfig:
    def __init__(self):
        self.settings = {}

    def load_settings(self, file_path):
        with open(file_path, "r") as file:
            self.settings = yaml.load(file, Loader=yaml.FullLoader)
