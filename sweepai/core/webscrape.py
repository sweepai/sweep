import re

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.sync_api import sync_playwright
from tqdm import tqdm

from sweepai.logn import logger


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
        'button[aria-label="Scroll back to top"]',
        "aside.theme-doc-sidebar-container",
        "div.theme-doc-toc-mobile",
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
    
    markdown_content = md(content, heading_style="ATX")
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

    return {"meta": meta, "title": title, "content": markdown_content}


def webscrape(BASE_URL_PREFIX):
    visited_urls = set()
    queued_urls = set()
    pbar = tqdm(total=1, desc="Scraping pages")

    all_files = {}

    def scrape_page(page, url):
        if url in visited_urls:
            return
        visited_urls.add(url)
        page.goto(url)
        content = page.content()

        result = parse_html(content)
        content = result["content"]
        url = re.sub(r"#.*", "", url)
        url = url.rstrip("/")
        pbar.update(1)

        all_files[url] = content

        all_links = page.eval_on_selector_all("a", "els => els.map(el => el.href)")
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
            try:
                scrape_page(page, link)
            except SystemExit:
                raise SystemExit
            except:
                logger.warning(f"Failed to scrape {link}")

    with sync_playwright() as p:
        browser = p.chromium.launch(timeout=0)
        page = browser.new_page()
        scrape_page(page, BASE_URL_PREFIX)
        browser.close()
    return all_files
