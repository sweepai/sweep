import os

__version__ = os.getenv('SWEEP_VERSION', 'unknown')

def get_version():
    return __version__
