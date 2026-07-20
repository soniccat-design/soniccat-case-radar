from __future__ import annotations

from typing import Any, Dict, List, Tuple

from src.models import Candidate
from src.utils.text import keyword_hit, normalize_title


GENERIC_REJECT_WORDS = [
    "poster",
    "海报",
    "wallpaper",
    "lookbook",
    "outfit",
    "穿搭",
    "街拍",
    "celebrity",
    "lifestyle",
    "collection campaign",
]

CATEGORY_HINTS = {
    "professional-running": {
        "positive": ["running", "racing", "marathon", "carbon", "elite", "跑鞋", "竞速", "马拉松", "碳板"],
        "negative": ["outsole only", "鞋底图", "sole only", "spike", "钉鞋"],
    },
    "running-outsole": {
        "positive": ["outsole", "sole", "traction", "rubber", "carbon plate", "鞋底", "底片", "大底", "底纹", "镂空"],
        "negative": ["portrait", "穿搭", "侧面穿着"],
    },
    "professional-spikes": {
        "positive": ["spike", "track", "sprint", "distance", "田径", "钉鞋", "钉板", "钉孔"],
        "negative": ["basketball", "篮球", "lifestyle", "casual", "休闲"],
    },
}


def basic_candidate_filter(candidate: Candidate, category: Dict[str, Any], image_config: Dict[str, Any]) -> Tuple[bool, str]:
    if not candidate.source_url or not candidate.image_url:
        return False, "missing url or image"
    if candidate.image_width and candidate.image_height:
        if candidate.image_width < int(image_config.get("min_width", 500)):
            return False, "image width too small"
        if candidate.image_height < int(image_config.get("min_height", 500)):
            return False, "image height too small"
    text = normalize_title(" ".join([candidate.title, candidate.summary, candidate.source_url, candidate.image_url]))
    if any(word in text for word in GENERIC_REJECT_WORDS):
        return False, "generic hard reject keyword"
    hints = CATEGORY_HINTS.get(category.get("id"), {})
    positives = list(hints.get("positive", [])) + list(category.get("keywords_zh", [])) + list(category.get("keywords_en", []))
    negatives = hints.get("negative", [])
    if any(normalize_title(word) in text for word in negatives):
        return False, "category reject keyword"
    if not keyword_hit(text, positives):
        return False, "category relevance keyword missing"
    return True, ""


def filter_candidates(candidates: List[Candidate], category: Dict[str, Any], image_config: Dict[str, Any]) -> List[Candidate]:
    result: List[Candidate] = []
    for candidate in candidates:
        passed, reason = basic_candidate_filter(candidate, category, image_config)
        if passed:
            result.append(candidate)
        else:
            candidate.metadata["filtered_reason"] = reason
    return result
