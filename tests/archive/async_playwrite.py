import os
import re

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.async_api import async_playwright
from tqdm import tqdm

# BASE_URL_PREFIX = "https://python.langchain.com/docs/additional_resources"
# BASE_URL_PREFIX = "https://react.dev"
# BASE_URL_PREFIX = "https://platform.openai.com/docs"
BASE_URL_PREFIX = "https://docs.anthropic.com/claude/docs"
docs_name = "anthropic"
visited_urls = set()
queued_urls = set()


def parse_html(html):
    soup = BeautifulSoup(html, "lxml")

    meta_properties = [
        "og:description",
        "og:site_name",
        "og:title",
        "og:type",
        "og:url",
    ]

    meta = {}
    links = []

    for a in soup.find_all("a", href=True):
        links.append({"title": a.text.strip(), "link": a["href"]})
    meta["links"] = links

    for property_name in meta_properties:
        try:
            tag = soup.find("meta", property=property_name)
            if tag:
                meta[property_name] = str(tag.get("content", None))
        except AttributeError:
            meta[property_name] = None

    for ignore_tag in soup(["noscript", "script", "style", "br"]):
        ignore_tag.decompose()

    selectors_to_skip = [
        "div[aria-hidden]",
        "nav",
        "header",
        # based on Docusaurus
        'div[aria-label="Skip to main content"]',
        "div.hidden",
        # 'nav[aria-label="Main"].navbar.navbar--fixed-top',
        'button[aria-label="Scroll back to top"]',
        "aside.theme-doc-sidebar-container",
        "div.theme-doc-toc-mobile",
        # 'nav[aria-label="Breadcrumbs"].theme-doc-breadcrumbs',
        # 'nav[aria-label="Docs pages navigation"].pagination-nav',
        # 'nav[aria-label="navigation"]',
        "div.thin-scrollbar.theme-doc-toc-desktop",
        "footer.footer",
        # for OpenAI
        "div.docs-nav",
        "div.pheader",
        "div.notice",
        # for Anthropic
        "div#ssr-top",
    ]

    for selector in selectors_to_skip:
        for tag in soup.select(selector):
            tag.decompose()

    title = soup.title.string if soup.title else ""
    content = str(soup.body) if soup.body else ""
    # print(soup.body)
    # quit()
    markdown_content = md(content, heading_style="ATX")
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

    return {"meta": meta, "title": title, "content": markdown_content}


pbar = tqdm(total=1, desc="Scraping pages")

all_files = {}


async def scrape_page(page, url):
    if url in visited_urls:
        return

    visited_urls.add(url)
    await page.goto(url)
    content = await page.content()

    result = parse_html(content)
    content = result["content"]

    url = re.sub(r"#.*", "", url)
    path = url[len(BASE_URL_PREFIX) :]
    if not path or path[path.rfind("/") :] == "/":
        path += "/index"
    # path = "langchain_docs" + path + ".md"
    path = f"scraped_docs/{docs_name}" + path + ".md"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    all_files[path] = content
    with open(path, "w") as f:
        f.write(content)
    pbar.update(1)

    all_links = await page.eval_on_selector_all("a", "els => els.map(el => el.href)")
    links = []
    for link in all_links:
        if "#" in link:
            link = link[: link.rfind("#")]
        link.rstrip("/")
        if (
            link.startswith(BASE_URL_PREFIX)
            and link not in visited_urls
            and link not in queued_urls
        ):
            queued_urls.add(link)
            links.append(link)
    links = list(set(links))

    pbar.total += len(links)

    for link in links:
        await scrape_page(page, link)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await scrape_page(page, BASE_URL_PREFIX)
        await browser.close()
