from dataclasses import dataclass
import json


@dataclass
class DockerfileConfig:
    dockerfile_path: str
    image_name: str # not sure if both are needed, but the intention is to clean up the image after the container is done
    container_name: str
    command: str

def load_dockerfile_configs_from_path(location) -> DockerfileConfig:
    # load an instance of this from a json file
    with open(location, 'r') as f:
        data = json.load(f)
    return [DockerfileConfig(**item) for item in data]