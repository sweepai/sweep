import docker
import uuid

client = docker.from_env()


class SandboxContainer:
    def __init__(self, *args, **kwargs):
        self.container_name = "sandbox-{}".format(str(uuid.uuid4()))

    def __enter__(self):
        client.containers.run(
            "sweepai/sandbox:latest",
            "tail -f /dev/null",
            detach=True,
            name=self.container_name,
        )  # keeps the container running
        self.container = client.containers.get(self.container_name)
        return self.container

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.container.stop()
        self.container.remove(force=True)
