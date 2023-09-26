import re

import requests
from bs4 import BeautifulSoup

# from llama_index import download_loader


def parse_html(html):
    soup = BeautifulSoup(html)

    meta_properties = [
        "og:description",
        "og:site_name",
        "og:title",
        "og:type",
        "og:url",
    ]

    meta = {}

    for property_name in meta_properties:
        try:
            tag = soup.find("meta", property=property_name)
            if tag:
                meta[property_name] = str(tag.get("content", None))
        except AttributeError:
            meta[property_name] = None

    for ignore_tag in soup(["script", "style"]):
        ignore_tag.decompose()

    title = soup.title.string if soup.title else ""
    content = soup.body.get_text() if soup.body else ""
    links = []

    for a in soup.find_all("a", href=True):
        links.append({"title": a.text.strip(), "link": a["href"]})

    content = re.sub(r"[\n\r\t]+", "\n", content)
    content = re.sub(r" +", " ", content)
    content = re.sub(r"[\n ]{3,}", "\n\n", content)
    content = content.strip()

    return {"meta": meta, "title": title, "content": content}


def download_html(url: str) -> str:
    # SimpleWebPageReader = download_loader("SimpleWebPageReader")
    # loader = SimpleWebPageReader()
    # document, *_ = loader.load_data(urls=[url])
    # return document.text
    return requests.get(url).text


def extract_info(url):
    html = download_html(url)
    data = parse_html(html)
    return data


def extract_links(text):
    pattern = r"\b(?:(?:https?|ftp)://|www\.)\S+\b"
    return list(set(re.findall(pattern, text)))
