from sweepai.utils.config import SweepConfig

yaml_string = """
# This is a full line comment
include_dirs: []
"""
config = SweepConfig.from_yaml(yaml_string)
import pdb; pdb.set_trace()
print(config)