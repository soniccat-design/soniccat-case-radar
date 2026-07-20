from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set
from urllib.parse import urljoin

from src.collectors.base import BaseCollector
from src.collectors.http import (
    HttpClient,
    expand_search_path,
    extract_domain,
    extract_links,
    extract_page_metadata,
    parse_rss,
    parse_sitemap,
)
from src.models import Candidate
from src.utils.dates import within_days
from src.utils.text import content_hash, keyword_hit, normalize_model_name, normalize_space


class GenericWebCollector(BaseCollector):
    adapter_name = "generic_web"

    def collect(self, category: Dict[str, Any], days: int) -> List[Candidate]:
        timeout = int(self.source_config.get("timeout_seconds") or self.global_config.get("image", {}).get("request_timeout_seconds", 20))
        retries = int(self.source_config.get("retry_count", 1))
        client = HttpClient(timeout=timeout, retries=retries)
        keywords = list(category.get("keywords_zh", [])) + list(category.get("keywords_en", []))
        candidates: List[Candidate] = []
        seen: Set[str] = set()
        max_candidates = int(self.source_config.get("max_candidates_per_category", 20))

        for domain in self.source_config.get("domains", []):
            root = "https://%s" % domain
            candidate_urls = self._discover_urls(client, root, domain, keywords, days)
            for page_url, published_hint in candidate_urls:
                if page_url in seen:
                    continue
                seen.add(page_url)
                if len(candidates) >= max_candidates:
                    return candidates
                try:
                    response = client.get(page_url)
                    meta = extract_page_metadata(response.url, response.text)
                    title = meta.get("title") or page_url
                    haystack = " ".join([title, meta.get("description", ""), response.url])
                    if not keyword_hit(haystack, keywords):
                        continue
                    published_at = meta.get("published_at") or published_hint
                    if published_at and not within_days(published_at, days):
                        continue
                    image_url = meta.get("image_url", "")
                    if not image_url:
                        continue
                    candidates.append(
                        Candidate(
                            category=category["id"],
                            title=normalize_space(title),
                            source_url=response.url,
                            source_domain=extract_domain(response.url),
                            source_type=self.source_type,
                            image_url=image_url,
                            model_name=meta.get("model_name") or title,
                            summary=meta.get("description", ""),
                            published_at=published_at,
                            source_id=self.source_id,
                            source_priority=int(self.source_config.get("priority", 50)),
                            content_hash=content_hash(title, response.url, image_url),
                            normalized_model_name=normalize_model_name(meta.get("model_name") or title),
                            metadata={"collector": self.adapter_name},
                        )
                    )
                except Exception:
                    continue
        return candidates

    def _discover_urls(
        self,
        client: HttpClient,
        root: str,
        domain: str,
        keywords: Iterable[str],
        days: int,
    ) -> List[tuple]:
        rows: List[tuple] = []
        rows.extend(self._from_rss(client, root, keywords, days))
        rows.extend(self._from_sitemap(client, root, keywords, days))
        rows.extend(self._from_search_and_listing(client, root, domain, keywords))
        unique: List[tuple] = []
        seen = set()
        for url, published_at in rows:
            if url not in seen:
                seen.add(url)
                unique.append((url, published_at))
        return unique

    def _from_sitemap(self, client: HttpClient, root: str, keywords: Iterable[str], days: int) -> List[tuple]:
        rows: List[tuple] = []
        for path in self.source_config.get("sitemap_paths", []):
            try:
                response = client.get(urljoin(root, path), accept="application/xml,text/xml,*/*")
            except Exception:
                continue
            for loc, lastmod in parse_sitemap(response.text, limit=120):
                if lastmod and not within_days(lastmod, days):
                    continue
                if keyword_hit(loc, keywords):
                    rows.append((loc, lastmod))
        return rows

    def _from_rss(self, client: HttpClient, root: str, keywords: Iterable[str], days: int) -> List[tuple]:
        rows: List[tuple] = []
        for path in self.source_config.get("rss_paths", []):
            try:
                response = client.get(urljoin(root, path), accept="application/rss+xml,application/xml,text/xml,*/*")
            except Exception:
                continue
            for item in parse_rss(response.text, root, limit=80):
                if item.get("published_at") and not within_days(item["published_at"], days):
                    continue
                if keyword_hit(" ".join([item.get("title", ""), item.get("summary", ""), item.get("url", "")]), keywords):
                    rows.append((item["url"], item.get("published_at", "")))
        return rows

    def _from_search_and_listing(self, client: HttpClient, root: str, domain: str, keywords: Iterable[str]) -> List[tuple]:
        rows: List[tuple] = []
        paths = []
        paths.extend(self.source_config.get("search_paths", []))
        paths.extend(self.source_config.get("product_paths", []))
        paths.extend(self.source_config.get("category_paths", []))
        for path in paths:
            expanded_paths = [path]
            if "{keyword}" in path:
                expanded_paths = [path.replace("{keyword}", keyword) for keyword in list(keywords)[:4]]
            for expanded in expanded_paths:
                url = expand_search_path(root, expanded, "") if "{keyword}" not in expanded else expand_search_path(root, expanded, "")
                try:
                    response = client.get(url)
                except Exception:
                    continue
                for link in extract_links(response.url, response.text, [domain], limit=60):
                    if keyword_hit(link, keywords):
                        rows.append((link, ""))
        return rows


class BrandSiteCollector(GenericWebCollector):
    adapter_name = "brand_site"


class MediaSiteCollector(GenericWebCollector):
    adapter_name = "media_site"
