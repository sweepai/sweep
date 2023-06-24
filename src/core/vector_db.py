import toml
from src.utils.config import SweepConfig

def get_exclude_directories():
    config = toml.load("sweep.toml")
    sweep_config = SweepConfig(**config)
    return sweep_config.exclude_dirs

def index_files():
    exclude_directories = get_exclude_directories()
    # Rest of the indexing code, using exclude_directories to ignore specified directories