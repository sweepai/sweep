import os
import json
import subprocess
import time

global_id = 1

LSP_START_COMMANDS = {
    "python": ["pylsp"],
    "typescript": ["npx", "typescript-language-server", "--stdio"],
}

DISABLED_SOURCES = ["pycodestyle", "mccabe"] # Generally not useful for our purposes

class LSPConnection:
    DEFAULT_HOST = "0.0.0.0:2087"

    def __init__(
        self,
        directory: str,
        file_path: str | None = None,
        content: str | None = None,
        language: str | None = None
    ):
        self.directory = directory
        self.file_path = os.path.join(directory, file_path)
        self.content = content
        self.lsp_process = None
        self.language = language
        if not self.language:
            self.language = "python" if file_path.endswith(".py") else "typescript"

    def __enter__(self):
        print("Starting LSP server...")
        self.start_server()
        if self.directory:
            self.send_request("initialize", {
                "processId": 1,
                "rootUri": f"file://{self.directory}",
                "capabilities": {
                    "textDocument": {
                        "synchronization": {
                            "didOpen": True,
                            "didChange": True,
                        },
                        "publishDiagnostics": {
                            "relatedInformation": True
                        },
                        "diagnostic": {
                            "dynamicRegistration": True,
                        },
                    },
                }
            })
            # response = self.receive_response()
            # print(response)
            # response = self.receive_response()
            # print(response)
        if self.file_path:
            content = self.content
            if not content:
                with open(self.file_path, "r") as file:
                    content = file.read()
            self.send_request("textDocument/didOpen", {
                "textDocument": {
                    "uri": f"file://{self.file_path}",
                    "languageId": "typescript",
                    "text": content,
                    "version": 1,
                }
            }, include_id=False)
            # response = self.receive_response()
            # print(response)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("Stopping LSP server...")
        self.stop_server()

    def start_server(self):
        self.lsp_process = subprocess.Popen(
            LSP_START_COMMANDS.get(self.language, LSP_START_COMMANDS["python"]),
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

    def send_request(self, method: str, params: dict, include_id: bool = True):
        global global_id
        contents = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        if include_id:
            contents["id"] = global_id
            global_id += 1
        message = json.dumps(contents)
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
        self.send_request("textDocument/didChange", {
            "textDocument": {
                "uri": f"file://{self.file_path}",
                "languageId": "typescript",
                "text": content,
                "version": 2,
            }
        }, include_id=False)
        for _ in range(max_iters):
            response = self.receive_response()
            if response.get("method") == "textDocument/publishDiagnostics":
                return render_diagnostics(response.get("params", {}).get("diagnostics", []))
        return None

def render_diagnostics(diagnostics: list[dict]):
    return "\n".join(
        f"{d['range']['start']['line']}:{d['range']['start']['character']} - {d['source']} - {d['message']}"
        for d in diagnostics if d.get("source") not in DISABLED_SOURCES
    )


if __name__ == "__main__":
    # Usage
    directory = "/mnt/sweep_benchmark/django__django-16635"
    file_path = f"django/db/migrations/autodetector.py"

    with LSPConnection(
        directory,
        file_path,
    ) as lsp:
        diagnostics = lsp.get_diagnostics()
        print(diagnostics)
    
    # Should expect AttributeError: 'CheckConstraint' object has no attribute 'fields'
