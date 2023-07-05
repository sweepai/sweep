import yaml

class RepoConfig:
    def __init__(self, config_path):
        self.config_path = config_path
        self.settings = None
        self.load_config()

    def load_config(self):
        with open(self.config_path, 'r') as config_file:
            self.settings = yaml.safe_load(config_file)
