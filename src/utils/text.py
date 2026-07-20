from __future__ import annotations

import hashlib
import re
from typing import Iterable
from urllib.parse import urlparse


BRAND_WORDS = [
    "nike",
    "adidas",
    "asics",
    "new balance",
    "newbalance",
    "saucony",
    "hoka",
    "puma",
    "on",
    "brooks",
    "mizuno",
    "li-ning",
    "lining",
    "xtep",
    "anta",
    "361",
]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_title(value: str) -> str:
    value = normalize_space(value).lower()
    value = re.sub(r"[™®©]", "", value)
    value = re.sub(r"[\[\]【】()（）|｜:：,，.!！?？/\\\\]+", " ", value)
    return normalize_space(value)


def normalize_model_name(value: str) -> str:
    value = normalize_title(value)
    value = re.sub(r"\b(men'?s|women'?s|kids|男款|女款|男女|鞋|shoes?|running|跑鞋|review|评测|new|新品)\b", " ", value)
    value = re.sub(r"\b(v|version)\s*([0-9]+)\b", r"v\2", value)
    return normalize_space(value)


def extract_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def stable_hash(*parts: str, length: int = 16) -> str:
    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


def content_hash(title: str, url: str, image_url: str = "") -> str:
    return stable_hash(normalize_title(title), url.strip(), image_url.strip(), length=32)


def slugify(value: str) -> str:
    value = normalize_title(value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    return value or "case"


def keyword_hit(text: str, keywords: Iterable[str]) -> bool:
    haystack = normalize_title(text)
    return any(normalize_title(keyword) in haystack for keyword in keywords if keyword)


def chinese_char_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))


def clamp_reason(reason: str, min_chars: int, max_chars: int) -> str:
    reason = re.sub(r"[。！？!?.]+$", "", normalize_space(reason))
    chars = re.findall(r"[\u4e00-\u9fff]", reason)
    if len(chars) <= max_chars:
        return reason
    count = 0
    output = []
    for char in reason:
        if "\u4e00" <= char <= "\u9fff":
            count += 1
        if count > max_chars:
            break
        output.append(char)
    return "".join(output).rstrip("，、；： ")
