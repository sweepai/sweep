from dataclasses import dataclass
import json
import os
import subprocess
from collections import defaultdict
from loguru import logger
from redis import Redis

@dataclass
class CTags:
    sha: str | None = None
    redis_instance: Redis | None = None
    ctags_cmd = [
        "ctags",
        "--fields=+S",
        "--extras=-F",
        "--output-format=json",
        "--output-encoding=utf-8",
    ]
    files = []
    def run_ctags(self, filename: str) -> list[dict]:
        cmd = self.ctags_cmd + [
            "--input-encoding=utf-8",
            filename
        ]
        ctags_cache_key = f"ctags-{self.sha}{filename}"
        cache_hit = self.redis_instance.get(ctags_cache_key)
        if cache_hit:
            logger.info(f"Cache hit for {ctags_cache_key}")
            data = json.loads(cache_hit)
        else:
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
            # set cache
            self.redis_instance.set(ctags_cache_key, json.dumps(data))
        return data
