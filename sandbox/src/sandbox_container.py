import uuid

import docker

client = docker.from_env()


class SandboxContainer:
    def __init__(self, image_id="sweepai/sandbox:latest"):
        self.container_name = "sandbox-{}".format(str(uuid.uuid4()))
        self.image_id = image_id

    def __enter__(self):
        client.containers.run(
            self.image_id,
            "tail -f /dev/null",
            detach=True,
            name=self.container_name,
        )  # keeps the container running
        self.container = client.containers.get(self.container_name)
        return self.container

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.container.stop()
        self.container.remove(force=True)

    @staticmethod
    def image_exists(image_id):
        try:
            client.images.get(image_id)
            return True
        except docker.errors.ImageNotFound:
            return False
