from __future__ import annotations

import time
from typing import Any, Dict, List
from urllib.parse import quote_plus

from src.collectors.base import BaseCollector
from src.models import Candidate
from src.utils.dates import iso_now
from src.utils.text import content_hash, extract_domain, keyword_hit, normalize_model_name, normalize_space


class XiaohongshuCollector(BaseCollector):
    adapter_name = "xiaohongshu"

    def collect(self, category: Dict[str, Any], days: int) -> List[Candidate]:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:
            raise RuntimeError("Playwright unavailable for Xiaohongshu public pages: %s" % exc)

        keywords = list(category.get("keywords_zh", [])) + list(category.get("keywords_en", []))
        max_candidates = int(self.source_config.get("max_candidates_per_category", 12))
        retry_count = int(self.source_config.get("retry_count", 2))
        timeout_ms = int(self.source_config.get("timeout_seconds", 25)) * 1000
        search_template = self.source_config.get("search_url", "https://www.xiaohongshu.com/search_result?keyword={keyword}")
        candidates: List[Candidate] = []
        seen = set()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(storage_state=None, locale="zh-CN")
            try:
                for keyword in keywords[:5]:
                    if len(candidates) >= max_candidates:
                        break
                    url = search_template.replace("{keyword}", quote_plus(keyword))
                    last_error = None
                    for attempt in range(retry_count + 1):
                        page = context.new_page()
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                            page.wait_for_timeout(1800)
                            candidates.extend(
                                self._extract_from_page(page, category, keyword, keywords, seen, max_candidates - len(candidates))
                            )
                            page.close()
                            break
                        except Exception as exc:
                            last_error = exc
                            page.close()
                            if attempt < retry_count:
                                time.sleep(0.8 * (attempt + 1))
                    if last_error and len(candidates) == 0:
                        continue
            finally:
                context.close()
                browser.close()
        return candidates[:max_candidates]

    def _extract_from_page(self, page: Any, category: Dict[str, Any], keyword: str, keywords: List[str], seen: set, remaining: int) -> List[Candidate]:
        rows: List[Candidate] = []
        cards = page.locator("a").evaluate_all(
            """
            (anchors) => anchors.slice(0, 80).map((a) => {
              const img = a.querySelector('img');
              const title = a.innerText || a.getAttribute('title') || (img && img.getAttribute('alt')) || '';
              return {
                href: a.href || '',
                title,
                image: img ? (img.currentSrc || img.src || '') : ''
              };
            })
            """
        )
        for item in cards:
            if len(rows) >= remaining:
                break
            href = normalize_space(item.get("href", ""))
            image = normalize_space(item.get("image", ""))
            title = normalize_space(item.get("title", "")) or keyword
            if not href or not image or href in seen:
                continue
            haystack = " ".join([title, href, keyword])
            if not keyword_hit(haystack, keywords):
                continue
            seen.add(href)
            rows.append(
                Candidate(
                    category=category["id"],
                    title=title,
                    source_url=href,
                    source_domain=extract_domain(href) or "xiaohongshu.com",
                    source_type=self.source_type,
                    image_url=image,
                    model_name=title,
                    summary="",
                    published_at="",
                    captured_at=iso_now(),
                    source_id=self.source_id,
                    source_priority=int(self.source_config.get("priority", 82)),
                    content_hash=content_hash(title, href, image),
                    normalized_model_name=normalize_model_name(title),
                    metadata={"collector": self.adapter_name, "keyword": keyword},
                )
            )
        return rows
