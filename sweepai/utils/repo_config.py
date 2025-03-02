import yaml

class RepoConfig:
    def __init__(self, config_path):
        self.config_path = config_path
        self.settings = None
        self.load_config()

    def load_config(self):
        try:
            with open(self.config_path, 'r') as config_file:
                self.settings = yaml.safe_load(config_file)
        except FileNotFoundError:
            print(f"Configuration file {self.config_path} not found.")
        except yaml.YAMLError:
            print(f"Error parsing YAML file {self.config_path}.")

