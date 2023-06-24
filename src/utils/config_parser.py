import toml

def parse_sweep_toml(file_path):
    """
    Parse a sweep.toml configuration file and return a dictionary of the configurations.

    Args:
        file_path (str): The path to the sweep.toml file.

    Returns:
        dict: A dictionary of the parsed configurations.
    """
    with open(file_path, 'r') as file:
        config = toml.load(file)
    return config