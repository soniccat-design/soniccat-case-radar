from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional


CN_TZ = timezone(timedelta(hours=8))


def now_cn() -> datetime:
    return datetime.now(CN_TZ)


def iso_now() -> str:
    return now_cn().isoformat(timespec="seconds")


def parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except Exception:
        return None


def within_days(value: str, days: int, now: Optional[datetime] = None) -> bool:
    parsed = parse_datetime(value)
    if not parsed:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CN_TZ)
    current = now or now_cn()
    return parsed >= current - timedelta(days=days)


def age_days(value: str, now: Optional[datetime] = None) -> int:
    parsed = parse_datetime(value)
    if not parsed:
        return 999
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CN_TZ)
    current = now or now_cn()
    return max(0, (current - parsed).days)
