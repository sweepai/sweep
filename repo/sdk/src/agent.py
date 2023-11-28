import os

from openai import OpenAI

# Check if the OPENAI_API_KEY environment variable is set
if "OPENAI_API_KEY" not in os.environ:
    raise Exception("OPENAI_API_KEY environment variable not set")

# Set the OpenAI API key
OpenAI.api_key = os.environ["OPENAI_API_KEY"]
