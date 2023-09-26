import json
import re

import requests
from bs4 import BeautifulSoup


def get_html(url):
    response = requests.get(url)
    return response.text


def parse_html(html):
    soup = BeautifulSoup(html)

    meta = {
        "og:description": str(
            soup.find("meta", property="og:description").get("content", None)
        ),
        "og:site_name": str(
            soup.find("meta", property="og:site_name").get("content", None)
        ),
        "og:title": str(soup.find("meta", property="og:title").get("content", None)),
        "og:type": str(soup.find("meta", property="og:type").get("content", None)),
        "og:url": str(soup.find("meta", property="og:url").get("content", None)),
    }

    for ignore_tag in soup(["script", "style"]):
        ignore_tag.decompose()

    title = soup.title.string
    content = soup.body.get_text()
    links = []

    for a in soup.find_all("a", href=True):
        links.append({"title": a.text.strip(), "link": a["href"]})

    content = re.sub(r"[\n\r\t]+", "\n", content)
    content = re.sub(r" +", " ", content)
    content = re.sub(r"[\n ]{3,}", "\n\n", content)
    content = content.strip()

    return {"meta": meta, "title": title, "content": content}


def extract_info(url):
    html = get_html(url)
    data = parse_html(html)
    return json.dumps(data, indent=4, sort_keys=True)


url = "https://stackoverflow.com/questions/63997423/finding-nth-fibonacci-number-in-ologn-time-and-space-complexity"
print(extract_info(url))
