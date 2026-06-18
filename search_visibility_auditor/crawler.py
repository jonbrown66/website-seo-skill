from __future__ import annotations

import json
import re
import time
from html.parser import HTMLParser
from urllib import robotparser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .models import PageSnapshot
from .security import SecurityError, validate_public_url
from .utils import normalize_url, same_domain


class SimpleHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self._in_title = False
        self.meta_description = ""
        self.canonical = ""
        self.noindex = False
        self.headings: dict[str, list[str]] = {f"h{i}": [] for i in range(1, 7)}
        self._heading: str | None = None
        self._heading_text: list[str] = []
        self.links: list[str] = []
        self.images_missing_alt: list[str] = []
        self.schema_blocks: list[str] = []
        self._schema = False
        self._schema_text: list[str] = []
        self.visible_text: list[str] = []
        self._skip_text = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript"}:
            self._skip_text = True
        if tag == "meta":
            name = (attributes.get("name") or attributes.get("property") or "").lower()
            content = attributes.get("content", "")
            if name == "description":
                self.meta_description = content.strip()
            if name == "robots" and "noindex" in content.lower():
                self.noindex = True
        if tag == "link" and attributes.get("rel", "").lower() == "canonical":
            self.canonical = normalize_url(attributes.get("href", ""), self.base_url)
        if tag in self.headings:
            self._heading = tag
            self._heading_text = []
        if tag == "a" and attributes.get("href"):
            self.links.append(normalize_url(attributes["href"], self.base_url))
        if tag == "img" and not attributes.get("alt", "").strip():
            self.images_missing_alt.append(urljoin(self.base_url, attributes.get("src", "")))
        if tag == "script" and "ld+json" in attributes.get("type", "").lower():
            self._schema = True
            self._schema_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript"}:
            self._skip_text = False
        if self._heading == tag:
            text = " ".join(" ".join(self._heading_text).split())
            if text:
                self.headings[tag].append(text)
            self._heading = None
        if tag == "script" and self._schema:
            text = "".join(self._schema_text).strip()
            if text:
                self.schema_blocks.append(text)
            self._schema = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._heading:
            self._heading_text.append(data)
        if self._schema:
            self._schema_text.append(data)
        elif not self._skip_text:
            stripped = data.strip()
            if stripped:
                self.visible_text.append(stripped)


def fetch_url(url: str, user_agent: str, timeout: int, max_bytes: int = 2_000_000, retries: int = 1) -> tuple[int, str, str, str]:
    last_error: Exception | None = None
    safe_url = validate_public_url(url)
    for attempt in range(retries + 1):
        try:
            request = Request(safe_url, headers={"User-Agent": user_agent})
            with urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("content-type", "")
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise SecurityError("Response body exceeds configured maximum")
                charset = response.headers.get_content_charset() or "utf-8"
                return response.status, response.geturl(), content_type, body.decode(charset, errors="replace")
        except HTTPError as exc:
            body = exc.read(max_bytes).decode("utf-8", errors="replace")
            return exc.code, exc.geturl(), exc.headers.get("content-type", ""), body
        except (URLError, TimeoutError, SecurityError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.25 * (2**attempt))
    raise SecurityError(str(last_error))


def parse_page(url: str, status_code: int, final_url: str, content_type: str, html: str) -> PageSnapshot:
    parser = SimpleHTMLParser(final_url)
    parser.feed(html)
    links = [link for link in parser.links if urlparse(link).scheme in {"http", "https"}]
    internal = sorted({link for link in links if same_domain(link, final_url)})
    external = sorted({link for link in links if not same_domain(link, final_url)})
    word_count = len(re.findall(r"\b[\w'-]+\b", " ".join(parser.visible_text)))
    return PageSnapshot(
        url=url,
        status_code=status_code,
        final_url=normalize_url(final_url),
        content_type=content_type,
        html=html,
        title=" ".join(parser.title.split()),
        meta_description=parser.meta_description,
        canonical=parser.canonical,
        headings=parser.headings,
        links_internal=internal,
        links_external=external,
        images_missing_alt=parser.images_missing_alt,
        schema_blocks=parser.schema_blocks,
        word_count=word_count,
        noindex=parser.noindex,
    )


def robots_allowed(root_url: str, target_url: str, user_agent: str, timeout: int) -> tuple[bool, str]:
    robots_url = urljoin(root_url, "/robots.txt")
    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        status, _, _, body = fetch_url(robots_url, user_agent, timeout, max_bytes=500_000, retries=0)
        if status >= 400:
            return True, robots_url
        parser.parse(body.splitlines())
        return parser.can_fetch(user_agent, target_url), robots_url
    except Exception:
        return True, robots_url


def discover_sitemap_urls(root_url: str, user_agent: str, timeout: int, max_urls: int) -> list[str]:
    sitemap_url = urljoin(root_url, "/sitemap.xml")
    try:
        status, _, _, body = fetch_url(sitemap_url, user_agent, timeout, max_bytes=2_000_000, retries=0)
    except Exception:
        return []
    if status >= 400:
        return []
    urls = re.findall(r"<loc>\s*([^<]+)\s*</loc>", body, flags=re.I)
    return [normalize_url(url.strip()) for url in urls[:max_urls]]


def crawl_site(root_url: str, max_pages: int, timeout: int, user_agent: str, obey_robots: bool = True) -> tuple[list[PageSnapshot], dict]:
    root = normalize_url(validate_public_url(root_url))
    queue = [root]
    queue.extend(discover_sitemap_urls(root, user_agent, timeout, max_pages))
    seen: set[str] = set()
    pages: list[PageSnapshot] = []
    robots_meta: dict = {"checked": obey_robots, "blocked": []}
    while queue and len(pages) < max_pages:
        url = normalize_url(queue.pop(0))
        if url in seen or not same_domain(url, root):
            continue
        seen.add(url)
        if obey_robots:
            allowed, robots_url = robots_allowed(root, url, user_agent, timeout)
            robots_meta["url"] = robots_url
            if not allowed:
                robots_meta["blocked"].append(url)
                continue
        try:
            status, final_url, content_type, body = fetch_url(url, user_agent, timeout)
            if "html" not in content_type.lower() and "<html" not in body.lower():
                continue
            page = parse_page(url, status, final_url, content_type, body)
            pages.append(page)
            for link in page.links_internal:
                if len(queue) + len(seen) < max_pages * 3:
                    queue.append(link)
        except Exception as exc:
            pages.append(
                PageSnapshot(
                    url=url,
                    status_code=0,
                    final_url=url,
                    content_type="",
                    html="",
                    title="",
                    meta_description="",
                    canonical="",
                    headings={f"h{i}": [] for i in range(1, 7)},
                    links_internal=[],
                    links_external=[],
                    images_missing_alt=[],
                    schema_blocks=[],
                    word_count=0,
                    noindex=False,
                )
            )
            robots_meta.setdefault("errors", []).append({"url": url, "error": str(exc)})
    robots_meta["pages_discovered"] = len(seen)
    return pages, robots_meta


def validate_json_ld(block: str) -> bool:
    try:
        json.loads(block)
        return True
    except json.JSONDecodeError:
        return False

