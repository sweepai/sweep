from loguru import logger
from openai import OpenAI
import requests
import re
import base64

from sweepai.config.client import SweepConfig
from sweepai.utils.github_utils import get_token

# we must get the raw issue which contains the body html
def get_image_urls_from_issue(num: int, repo_full_name: str, installation_id: int):
    sweep_config = SweepConfig()
    token = get_token(installation_id)
    url = f"https://api.github.com/repos/{repo_full_name}/issues/{num}"
    headers = {
        "Accept": "application/vnd.github.full+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    urls = []
    try:
        response = requests.get(url, headers=headers)
        body_html = response.json()['body_html']
        image_url_regex = r'<img src="(?P<url>https?:[^"]+)"'
        image_url_matches = list(re.finditer(image_url_regex, body_html, re.DOTALL))
        for match in image_url_matches:
            url = match.group('url')
            # only accept png, jpg, jpeg or webp
            added = False
            for ext in sweep_config.allowed_image_types:
                if ext in url:
                    urls.append((url, ext))
                    added = True
                    break
            # unsupported type
            if not added:
                logger.error(f"Did not add image url: {url}\nReason: image type unsupported!")
    except Exception as e:
        logger.error(f"Encountered error while attempting to fetch raw issue {num} for {repo_full_name}:\n{e}")
    return urls


# gets image contents from a list of urls
def get_image_blobs_from_urls(urls: list[tuple[str, str]]):
    image_contents = []
    for url, image_type in urls:
        response = requests.get(url)
        if response.status_code == 200:
            image_contents.append((base64.b64encode(response.content).decode('utf-8'), image_type))
        else:
            image_contents.append((None, image_type))
    return image_contents

# sumarize images
def summarize_images(images: list[tuple[str, str]]):
    summaries = []
    client = OpenAI()
    for image, image_type in images:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What’s in this image?"},
                    {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{image_type};base64,{image}",
                        "detail": "high"
                    },
                    },
                ],
                }
            ],
            max_tokens=1024,
        )
        summaries.append(response.choices[0].message.content)

    return summaries

