from src.utils.config import SweepConfig

yaml_string = """
# This is a full line comment
include_dirs: []
"""

print(SweepConfig.from_yaml(yaml_string))