from __future__ import annotations

from typing import Any, Dict, Iterable, List

from src.models import Candidate
from src.utils.dates import age_days
from src.utils.text import keyword_hit


def score_candidate(candidate: Candidate, category: Dict[str, Any], weights: Dict[str, int], primary_days: int) -> float:
    total = 0.0
    total += _relevance_score(candidate, category) * weights.get("relevance", 40) / 40.0
    total += _image_score(candidate) * weights.get("image_quality", 25) / 25.0
    total += _freshness_score(candidate, primary_days) * weights.get("freshness", 20) / 20.0
    total += _source_trust_score(candidate) * weights.get("source_trust", 15) / 15.0
    candidate.score = min(100.0, round(total, 2))
    return candidate.score


def score_and_sort(candidates: Iterable[Candidate], category: Dict[str, Any], weights: Dict[str, int], primary_days: int) -> List[Candidate]:
    rows = list(candidates)
    for candidate in rows:
        score_candidate(candidate, category, weights, primary_days)
    return sorted(rows, key=lambda item: (item.score, item.source_priority), reverse=True)


def _relevance_score(candidate: Candidate, category: Dict[str, Any]) -> float:
    keywords = list(category.get("keywords_zh", [])) + list(category.get("keywords_en", []))
    text = " ".join([candidate.title, candidate.summary, candidate.source_url, candidate.image_url])
    base = 18.0
    hits = sum(1 for keyword in keywords if keyword_hit(text, [keyword]))
    base += min(14.0, hits * 4.0)
    if category.get("id") == "running-outsole" and keyword_hit(text, ["outsole", "sole", "鞋底", "底片", "大底"]):
        base += 8.0
    if category.get("id") == "professional-spikes" and keyword_hit(text, ["spike", "track", "钉鞋", "钉板"]):
        base += 8.0
    if category.get("id") == "professional-running" and keyword_hit(text, ["carbon", "marathon", "racing", "碳板", "马拉松", "竞速"]):
        base += 8.0
    return min(40.0, base)


def _image_score(candidate: Candidate) -> float:
    if not candidate.image_width or not candidate.image_height:
        return 16.0
    long_edge = max(candidate.image_width, candidate.image_height)
    short_edge = min(candidate.image_width, candidate.image_height)
    score = 10.0
    if long_edge >= 1000:
        score += 7.0
    if short_edge >= 700:
        score += 5.0
    clarity = float(candidate.metadata.get("clarity", 0.0) or 0.0)
    if clarity >= 850:
        score += 3.0
    return min(25.0, score)


def _freshness_score(candidate: Candidate, primary_days: int) -> float:
    days = age_days(candidate.published_at or candidate.captured_at)
    if days <= 90:
        return 20.0
    if days <= primary_days:
        return 16.0
    if days <= 1095:
        return 10.0
    return 4.0


def _source_trust_score(candidate: Candidate) -> float:
    priority = max(0, min(100, int(candidate.source_priority or 50)))
    return round(priority / 100.0 * 15.0, 2)
