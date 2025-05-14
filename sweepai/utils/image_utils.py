from loguru import logger
from openai import OpenAI
import requests
import re
import base64

from sweepai.config.client import SweepConfig
from sweepai.utils.github_utils import get_installation_id, get_token

# we must get the raw issue which contains the body html and the actual links to the images
def get_image_urls_from_issue(num: int, repo_full_name: str, installation_id: int):
    sweep_config = SweepConfig()
    token = get_token(installation_id)
    url = f"https://api.github.com/repos/{repo_full_name}/issues/{num}"
    headers = {
        "Accept": "application/vnd.github.full+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    urls = {}
    try:
        response = requests.get(url, headers=headers)
        body_html = response.json()['body_html']
        if not body_html:
            return urls
        image_url_regex = r'<img.*?src="(?P<url>https?:[^"]+)"'
        image_url_matches = list(re.finditer(image_url_regex, body_html, re.DOTALL))
        for match in image_url_matches:
            url = match.group('url').strip()
            # only accept png, jpg, jpeg or webp
            added = False
            # breakpoint()
            for ext in sweep_config.allowed_image_types:
                if ext in url:
                    urls[url] = ext
                    added = True
                    break
            # unsupported type
            if not added:
                logger.warning(f"Did not add image url: {url}\nReason: image type unsupported!")
    except Exception as e:
        logger.error(f"Encountered error while attempting to fetch raw issue {num} for {repo_full_name}:\n{e}")
    return urls

# gets image contents from a list of urls
def get_image_contents_from_urls(urls: dict[str, str]):
    image_contents = {}
    for url, image_type in urls.items():
        response = requests.get(url)
        if response.status_code == 200:
            image_contents[url] = {
                "content": base64.b64encode(response.content).decode('utf-8'),
                "type": image_type
            }
        else:
            logger.error(f"Could not get contents for image: {url}")
    return image_contents

# use this function to get placeholder links to the images (what you get from the body of the issue)
# use this in conjunction with get_image_urls_from_issue to see where to place the images
def get_image_urls_from_issue_body(body: str) -> dict[str, str]:
    urls = {}
    image_url_regex = r'(?P<image_text>!\[.*?\]\((?P<url>https?:[^)]+)\))'
    image_url_matches = list(re.finditer(image_url_regex, body, re.DOTALL))

    for match in image_url_matches:
        urls[match.group('url').strip()] = match.group('image_text').strip()
    return urls

# sumarize images
def summarize_images(images: list[tuple[str, str]]):
    summaries = []
    client = OpenAI()
    for image, image_type, url in images:
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

def match_image_url_to_image_contents(image_urls: dict[str, str], image_contents: dict[str, dict[str, str]]):
    image_url_to_image_raw_urls = {}
    for image, image_data in image_contents.items():
        image_type = image_data['type']
        base_url = image.split(f".{image_type}")[0]
        ids = base_url.split(".com/")[-1] # this is slightly jank
        id1, id2 = ids.split("/")
        id2 = "-".join(id2.split("-")[1:])
        # match image_url based on this unique_id
        unique_id = f"{id1}/{id2}"
        for image_url in image_urls:
            if unique_id in image_url:
                image_url_to_image_raw_urls[image_url] = image
    return image_url_to_image_raw_urls

# turns a block of text into a message with images
def create_message_with_images(message: dict[str, str], images: dict[str, dict[str, str]], use_openai: bool = False):
    if not images:
        return message
    image_urls = get_image_urls_from_issue_body(message["content"])
    if not image_urls:
        return message
    # we have detected the presence of images, now we need to match our image with the actual image
    image_url_to_image_raw_urls = match_image_url_to_image_contents(image_urls, images)
    # now break the message up
    message_contents = message["content"]
    new_contents = []
    # now we find each place in the message contents our image texts show up
    markers = list(image_urls.items())
    positions = []
    for key, marker in markers:
        for match in re.finditer(re.escape(marker), message_contents):
            positions.append((match.start(), marker, key))
    positions.sort()

    last_pos = 0
    for pos, marker, image_url in positions:
        if image_url not in image_url_to_image_raw_urls:
            continue
        image_data = images[image_url_to_image_raw_urls[image_url]]
        if use_openai:
            new_contents.append({
                "type": "text",
                "text": message_contents[last_pos:pos] + "\nAn image has been attached below:"
            })
            # add our image block
            new_contents.append({
                "type" : "image_url",
                "image_url" : {
                    "url": f"data:image/{image_data['type']};base64,{image_data['content']}",
                    "detail": "high"
                }
            })
        else:
            new_contents.append({
                "type": "text",
                "text": message_contents[last_pos:pos] + "\nAn image has been attached below:"
            })
            # add our image block
            new_contents.append({
                "type" : "image",
                "source" : {
                    "type": "base64",
                    "media_type": f"image/{image_data['type']}",
                    "data": image_data["content"]
                }
            })
        last_pos = pos + len(marker)
    # add last bit
    if message_contents[last_pos:].strip():
        new_contents.append({
            "type": "text",
            "text": message_contents[last_pos:]
        })

    new_message = {
        "role": message["role"],
        "content": new_contents
    }
    return new_message

if __name__ == "__main__":
    repo_full_name = "org/repo"
    issue_number = 0
    org_name, repo_name = repo_full_name.split("/")
    installation_id = get_installation_id(org_name)
    image_urls = get_image_urls_from_issue(issue_number, repo_full_name, installation_id)
    image_contents = get_image_contents_from_urls(image_urls)
    breakpoint() # noqa


