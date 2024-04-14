import os
import json
import subprocess
import time
from websockets.sync.client import connect

class LSPConnection:
    DEFAULT_HOST = "0.0.0.0:2087"

    def __init__(
        self,
        directory: str,
        file_path: str | None = None,
        content: str | None = None
    ):
        self.directory = directory
        self.file_path = os.path.join(directory, file_path)
        self.content = content
        self.websocket = None
        self.lsp_process = None

    def __enter__(self):
        self.start_server()
        self.connect()
        if self.directory:
            self.send_request("initialize", {
                "processId": 1,
                "rootUri": f"file://{self.directory}",
                "capabilities": {}
            })
        if self.file_path:
            content = self.content
            if not content:
                with open(self.file_path, "r") as file:
                    content = file.read()
            self.send_request("textDocument/didOpen", {
                "textDocument": {
                    "uri": f"file://{self.file_path}",
                    "languageId": "python",
                    "text": content,
                    "version": 1,
                }
            })
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        self.stop_server()

    def start_server(self):
        self.lsp_process = subprocess.Popen(
            [
                "pylsp",
                "--ws",
                "--host", self.DEFAULT_HOST,
            ],
            cwd=self.directory
        )
        time.sleep(0.2)  # Allow some time for the server to start

    def connect(self):
        # Assuming `connect` is a method from a library that handles websocket connections
        self.websocket = connect(f"ws://{self.DEFAULT_HOST}")
        print("Connected to server!")

    def disconnect(self):
        if self.websocket:
            self.websocket.close()

    def stop_server(self):
        if self.lsp_process:
            self.lsp_process.kill()
            self.lsp_process.wait()

    def send_request(self, method, params):
        self.websocket.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }))
        response = self.websocket.recv()
        return json.loads(response)
    
    def get_diagnostics(
        self,
        max_iters: int = 10
    ):
        content = self.content
        if not content:
            with open(self.file_path, "r") as file:
                content = file.read()
        self.send_request("textDocument/didOpen", {
            "textDocument": {
                "uri": f"file://{self.file_path}",
                "languageId": "python",
                "text": content,
                "version": 1,
            }
        })
        for _ in range(max_iters):
            response = json.loads(self.websocket.recv())
            if response.get("method") == "textDocument/publishDiagnostics":
                return response.get("params", {}).get("diagnostics", [])
        return None


if __name__ == "__main__":
    # Usage
    directory = "/mnt/sweep_benchmark/django__django-11095"
    file_path = f"{directory}/tests/admin_inlines/test_inlines.py"

    with LSPConnection(
        directory,
        file_path,
        content="pass"
    ) as lsp:
        diagnostics = lsp.get_diagnostics()
        print(diagnostics)