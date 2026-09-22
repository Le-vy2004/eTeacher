"""Date parsing and freshness filtering utilities for Facebook posts."""
from datetime import datetime, timedelta
import re
from typing import Any

# Vietnamese and English relative time patterns
_TIME_PATTERNS = [
    (r"vừa xong|just now|moments ago", lambda m, now: now),
    (r"(\d+)\s*(?:phút|min|mins)\b", lambda m, now: now - timedelta(minutes=int(m.group(1)))),
    (r"(\d+)\s*(?:giờ|tiếng|hr|hrs|hours)\b", lambda m, now: now - timedelta(hours=int(m.group(1)))),
    (r"hôm qua|yesterday", lambda m, now: now - timedelta(days=1)),
    (r"(\d+)\s*(?:ngày|day|days|d)\b", lambda m, now: now - timedelta(days=int(m.group(1)))),
    (r"(\d+)\s*(?:tuần|week|weeks|w)\b", lambda m, now: now - timedelta(weeks=int(m.group(1)))),
    (r"(\d+)\s*(?:tháng|month|months|m)\b", lambda m, now: now - timedelta(days=int(m.group(1)) * 30)),
    (r"(\d+)\s*(?:năm|year|years|y)\b", lambda m, now: now - timedelta(days=int(m.group(1)) * 365)),
]


def parse_facebook_time(raw_time: str, reference_time: datetime | None = None) -> datetime:
    """Parse raw Facebook time string into a Python datetime object.

    Supports:
    - ISO 8601 strings (e.g. 2026-09-20T12:00:00Z)
    - Unix timestamps (in seconds or milliseconds)
    - Relative Vietnamese text: "vừa xong", "15 phút trước", "2 giờ trước", "hôm qua lúc 10:00", "3 ngày", "2 tuần", "1 tháng", "1 năm"
    - Vietnamese date formats: "15 tháng 9 lúc 14:00", "22 thg 8, 2025"
    """
    now = reference_time or datetime.now()
    if not raw_time or not isinstance(raw_time, str):
        return now

    cleaned = raw_time.strip()
    if not cleaned:
        return now

    # 1. Check numeric Unix timestamp
    digits_only = re.sub(r"\D", "", cleaned)
    if digits_only == cleaned and len(cleaned) in (10, 13):
        try:
            ts = int(cleaned)
            if len(cleaned) == 13:
                ts /= 1000.0
            return datetime.fromtimestamp(ts)
        except (ValueError, OverflowError, OSError):
            pass

    # 2. Check ISO 8601 format
    try:
        iso_clean = cleaned.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_clean)
    except (ValueError, TypeError):
        pass

    lower = cleaned.lower()

    # 3. Match relative time expressions
    for pattern, calculator in _TIME_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            try:
                return calculator(match, now)
            except Exception:
                pass

    # 4. Check "DD tháng MM" or "DD thg MM" (with optional year)
    # e.g., "15 tháng 9 lúc 08:30" or "20 thg 8, 2026"
    date_match = re.search(
        r"(\d{1,2})\s*(?:tháng|thg)\s*(\d{1,2})(?:[,\s]+(\d{4}))?",
        lower,
    )
    if date_match:
        try:
            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3)) if date_match.group(3) else now.year
            # If month > current month and no year specified, assume previous year
            if not date_match.group(3) and month > now.month:
                year = now.year - 1
            return datetime(year, month, day, now.hour, now.minute)
        except ValueError:
            pass

    # Fallback to current time if parsing could not determine date
    return now


def is_within_days(post_time: datetime, days: int = 30, reference_time: datetime | None = None) -> bool:
    """Check if post_time is within the last `days` days."""
    now = reference_time or datetime.now()
    cutoff = now - timedelta(days=days)
    return post_time >= cutoff
