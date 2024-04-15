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
        print("Starting LSP server...")
        self.start_server()
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
        print("Stopping LSP server...")
        self.stop_server()

    def start_server(self):
        self.lsp_process = subprocess.Popen(
            [
                "pylsp",
                # "--ws",
                # "--host", self.DEFAULT_HOST,
            ],
            cwd=self.directory,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def stop_server(self):
        if self.lsp_process:
            self.lsp_process.kill()
            self.lsp_process.wait()
            self.lsp_process = None

    def send_request(self, method, params):
        message = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        })
        self.lsp_process.stdin.write(
            f"Content-Length: {len(message)}\r\n\r\n{message}".encode("utf-8")
        )
        self.lsp_process.stdin.flush()
    
    def receive_response(self):
        headers = {}
        while True:
            line = self.lsp_process.stdout.readline().decode("utf-8")
            if not line.strip():
                break
            key, value = line.split(":")
            headers[key.strip()] = value.strip()
        
        content_length = int(headers["Content-Length"])
        body = self.lsp_process.stdout.read(content_length)
        return json.loads(body)
    
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
            response = self.receive_response()
            if response.get("method") == "textDocument/publishDiagnostics":
                return response.get("params", {}).get("diagnostics", [])
        return None

def render_diagnostics(diagnostics: list[dict]):
    return "\n".join(
        f"{d['range']['start']['line']}:{d['range']['start']['character']} - {d['message']}"
        for d in diagnostics
    )


if __name__ == "__main__":
    # Usage
    directory = "/mnt/sweep_benchmark/django__django-11095"
    file_path = f"{directory}/tests/admin_inlines/test_inlines.py"

    # process = subprocess.Popen(
    #     ['npx', 'typescript-language-server', '--stdio'],
    #     stdin=subprocess.PIPE,
    #     stdout=subprocess.PIPE,
    #     stderr=subprocess.PIPE,
    #     text=True
    # )

    # def send_request(method, params):
    #     # JSON-RPC header for content-length
    #     message = json.dumps({
    #         "jsonrpc": "2.0",
    #         "id": 1,
    #         "method": method,
    #         "params": params
    #     })
    #     content_length = len(message)
    #     process.stdin.write(f"Content-Length: {content_length}\r\n\r\n{message}")
    #     process.stdin.flush()

    # def receive_response():
    #     headers = {}
    #     # Read headers
    #     # while True:
    #     for line in process.stdout:
    #         if not line.strip():
    #             break
    #         key, value = line.split(":")
    #         headers[key.strip()] = value.strip()
        
    #     # Read the body
    #     content_length = int(headers["Content-Length"])
    #     body = process.stdout.read(content_length)
    #     return json.loads(body)

    # # Initialize the language server
    # send_request("initialize", {
    #     "processId": None,
    #     "capabilities": {},  # Specify capabilities based on what you need
    #     "trace": "off"
    # })

    # # Wait and print the response
    # response = receive_response()
    # print(response)


    with LSPConnection(
        directory,
        file_path,
        content="pass"
    ) as lsp:
        diagnostics = lsp.get_diagnostics()
        print(diagnostics)
