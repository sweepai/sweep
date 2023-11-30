from openai import OpenAI
from sweepai.config.server import OPENAI_API_KEY


client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
all_files = client.files.list()

for file in all_files:
    client.files.delete(file.id)
    file_mb = file.bytes / 1e6
    print(f"Deleted {file.id} which used {file_mb} megabytes")