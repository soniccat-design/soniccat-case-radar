from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import unescape
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

from src.utils.text import extract_domain, normalize_space


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; SonicCatCaseRadar/1.0; "
    "+https://github.com/sonic-cat/case-radar)"
)


@dataclass
class HttpResponse:
    url: str
    status_code: int
    text: str
    content: bytes
    headers: Dict[str, str]


class HttpClient:
    def __init__(self, timeout: int = 20, retries: int = 1, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent

    def get(self, url: str, accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8") -> HttpResponse:
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                return self._get_once(url, accept=accept)
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.6 * (attempt + 1))
        raise RuntimeError("GET failed for %s: %s" % (url, last_error))

    def _get_once(self, url: str, accept: str) -> HttpResponse:
        try:
            import requests  # type: ignore

            response = requests.get(
                url,
                timeout=(min(5, self.timeout), self.timeout),
                headers={"User-Agent": self.user_agent, "Accept": accept},
            )
            response.raise_for_status()
            return HttpResponse(
                url=response.url,
                status_code=response.status_code,
                text=response.text,
                content=response.content,
                headers={str(k).lower(): str(v) for k, v in response.headers.items()},
            )
        except ImportError:
            request = Request(url, headers={"User-Agent": self.user_agent, "Accept": accept})
            with urlopen(request, timeout=min(self.timeout, 8)) as response:  # nosec - configured public URLs only
                content = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return HttpResponse(
                    url=response.geturl(),
                    status_code=int(response.status),
                    text=content.decode(charset, errors="replace"),
                    content=content,
                    headers={str(k).lower(): str(v) for k, v in response.headers.items()},
                )


def absolute_url(base_url: str, maybe_url: str) -> str:
    return urljoin(base_url, maybe_url or "")


def extract_page_metadata(url: str, html: str) -> Dict[str, str]:
    title = _extract_title(html)
    description = _extract_meta(html, "description")
    og_title = _extract_meta(html, "og:title", attr="property")
    og_image = _extract_meta(html, "og:image", attr="property")
    og_description = _extract_meta(html, "og:description", attr="property")
    json_ld = _extract_json_ld(html)
    image = og_image or json_ld.get("image", "")
    name = json_ld.get("name", "")
    published = json_ld.get("datePublished", "") or json_ld.get("dateModified", "")
    return {
        "title": normalize_space(og_title or name or title),
        "description": normalize_space(og_description or description),
        "image_url": absolute_url(url, image) if image else "",
        "published_at": published,
        "model_name": normalize_space(name or og_title or title),
    }


def extract_links(url: str, html: str, allowed_domains: Iterable[str], limit: int = 80) -> List[str]:
    allowed = set(domain.lower() for domain in allowed_domains)
    links: List[str] = []
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")
        anchors = [anchor.get("href") for anchor in soup.find_all("a")]
    except Exception:
        anchors = re.findall(r"<a\s+[^>]*href=[\"']([^\"']+)[\"']", html, flags=re.I)
    for href in anchors:
        if not href:
            continue
        absolute = absolute_url(url, href)
        domain = extract_domain(absolute)
        if allowed and not any(domain == item or domain.endswith("." + item) for item in allowed):
            continue
        if absolute not in links:
            links.append(absolute)
        if len(links) >= limit:
            break
    return links


def parse_sitemap(xml_text: str, limit: int = 80) -> List[Tuple[str, str]]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    rows: List[Tuple[str, str]] = []
    for node in root.iter():
        if _local_name(node.tag) != "url":
            continue
        loc = ""
        lastmod = ""
        for child in node:
            name = _local_name(child.tag)
            if name == "loc":
                loc = (child.text or "").strip()
            elif name == "lastmod":
                lastmod = (child.text or "").strip()
        if loc:
            rows.append((loc, lastmod))
        if len(rows) >= limit:
            break
    return rows


def parse_rss(xml_text: str, base_url: str, limit: int = 80) -> List[Dict[str, str]]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    rows: List[Dict[str, str]] = []
    for node in root.iter():
        if _local_name(node.tag) not in ("item", "entry"):
            continue
        row = {"url": "", "title": "", "published_at": "", "summary": ""}
        for child in node:
            name = _local_name(child.tag)
            text = normalize_space(child.text or "")
            if name in ("title",):
                row["title"] = text
            elif name in ("link",):
                row["url"] = child.attrib.get("href") or text
            elif name in ("pubDate", "published", "updated"):
                row["published_at"] = text
            elif name in ("description", "summary", "content"):
                row["summary"] = re.sub(r"<[^>]+>", " ", unescape(text))
        if row["url"]:
            row["url"] = absolute_url(base_url, row["url"])
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def expand_search_path(root: str, path: str, keyword: str) -> str:
    return urljoin(root, path.replace("{keyword}", quote_plus(keyword)))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if not match:
        return ""
    return unescape(re.sub(r"\s+", " ", match.group(1))).strip()


def _extract_meta(html: str, name: str, attr: str = "name") -> str:
    patterns = [
        r'<meta[^>]+%s=["\']%s["\'][^>]+content=["\']([^"\']+)["\']' % (attr, re.escape(name)),
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+%s=["\']%s["\']' % (attr, re.escape(name)),
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.I | re.S)
        if match:
            return unescape(match.group(1)).strip()
    return ""


def _extract_json_ld(html: str) -> Dict[str, str]:
    matches = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    )
    for raw in matches:
        try:
            data = json.loads(unescape(raw.strip()))
        except Exception:
            continue
        found = _flatten_json_ld(data)
        if found:
            return found
    return {}


def _flatten_json_ld(data: object) -> Dict[str, str]:
    if isinstance(data, list):
        for item in data:
            found = _flatten_json_ld(item)
            if found:
                return found
        return {}
    if not isinstance(data, dict):
        return {}
    if "@graph" in data:
        found = _flatten_json_ld(data.get("@graph"))
        if found:
            return found
    image = data.get("image", "")
    if isinstance(image, list):
        image = image[0] if image else ""
    if isinstance(image, dict):
        image = image.get("url", "")
    return {
        "name": str(data.get("name", "") or data.get("headline", "")),
        "image": str(image or ""),
        "datePublished": str(data.get("datePublished", "")),
        "dateModified": str(data.get("dateModified", "")),
    }
