from dataclasses import dataclass
import json
import os
import subprocess
from collections import defaultdict


@dataclass
class Ctags:
    file: str
    ctags_cmd = [
        "ctags",
        "--fields=+S",
        "--extras=-F",
        "--output-format=json",
        "--output-encoding=utf-8",
    ]
    def run_ctags(self):
        cmd = self.ctags_cmd + [
            "--input-encoding=utf-8",
            self.file
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.PIPE).decode("utf-8")
        output_lines = output.splitlines()
        data = []
        for line in output_lines:
            try:
                tag = json.loads(line)
                if tag["_type"] == "tag":
                    data.append(tag)
            except json.decoder.JSONDecodeError as err:
                pass
        return data
