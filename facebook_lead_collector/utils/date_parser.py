"""Date parsing and freshness filtering utilities for Facebook posts."""
from datetime import datetime, timedelta
import re
from typing import Any

# Vietnamese and English relative time patterns
_TIME_PATTERNS = [
    (r"vừa xong|just now|moments ago", lambda m, now: now),
    (r"(\d+)\s*(?:phút|min|mins|p|m)\b", lambda m, now: now - timedelta(minutes=int(m.group(1)))),
    (r"(\d+)\s*(?:giờ|tiếng|hr|hrs|hours|h|g)\b", lambda m, now: now - timedelta(hours=int(m.group(1)))),
    (r"hôm qua|yesterday", lambda m, now: now - timedelta(days=1)),
    (r"(\d+)\s*(?:ngày|day|days|d)\b", lambda m, now: now - timedelta(days=int(m.group(1)))),
    (r"(\d+)\s*(?:tuần|week|weeks|w)\b", lambda m, now: now - timedelta(weeks=int(m.group(1)))),
    # "1 tháng" / "1 month" is treated as ~28 days to safely remain within the 1-month window
    (r"\b1\s*(?:tháng|month)\b", lambda m, now: now - timedelta(days=28)),
    (r"\b([1-9]|1[0-2])\s*(?:tháng|month|months)(?!\s*\d)\b", lambda m, now: now - timedelta(days=int(m.group(1)) * 30)),
    (r"(\d+)\s*(?:năm|year|years|y)\b", lambda m, now: now - timedelta(days=int(m.group(1)) * 365)),
]


def parse_facebook_time(
    raw_time: str | None,
    reference_time: datetime | None = None,
    fallback_to_now: bool = False,
) -> datetime | None:
    """Parse raw Facebook time string into a Python datetime object.

    Supports:
    - ISO 8601 strings (e.g. 2026-09-20T12:00:00Z)
    - Unix timestamps (in seconds or milliseconds)
    - Vietnamese date formats: "Thứ Ba, 22 Tháng 9, 2026 lúc 01:34", "15 tháng 9 lúc 14:00", "22 thg 8, 2025", "24/08/2026"
    - Relative Vietnamese text: "vừa xong", "15 phút trước", "20 giờ", "hôm qua lúc 10:00", "3 ngày", "2 tuần", "1 tháng", "1 năm"
    """
    now = reference_time or datetime.now()
    if not raw_time or not isinstance(raw_time, str):
        return now if fallback_to_now else None

    # Clean characters like bullet, globe icon, etc.
    cleaned = re.sub(r"[·•\u2022\u00b7\U0001f30e\U0001f310\U0001f30f]", " ", raw_time).strip()
    if not cleaned:
        return now if fallback_to_now else None

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

    # 3. Check "DD/MM" or "DD/MM/YYYY" format
    slash_match = re.search(r"(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{4}))?", lower)
    if slash_match and not re.search(r"\d+\s*giờ", lower):
        try:
            d = int(slash_match.group(1))
            m = int(slash_match.group(2))
            y = int(slash_match.group(3)) if slash_match.group(3) else now.year
            if 1 <= d <= 31 and 1 <= m <= 12:
                if not slash_match.group(3) and m > now.month:
                    y = now.year - 1
                return datetime(y, m, d)
        except ValueError:
            pass

    # 4. Check "DD tháng MM" or "DD thg MM" (with optional year and time) FIRST
    # e.g., "Thứ Ba, 22 Tháng 9, 2026 lúc 01:34", "15 tháng 9 lúc 08:30" or "20 thg 8, 2026"
    date_match = re.search(
        r"(\d{1,2})\s*(?:tháng|thg)\s*(\d{1,2})(?:[,\s]+(\d{4}))?(?:\s*(?:lúc|at)\s*(\d{1,2}):(\d{1,2}))?",
        lower,
    )
    if date_match:
        try:
            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3)) if date_match.group(3) else now.year
            hour = int(date_match.group(4)) if date_match.group(4) else now.hour
            minute = int(date_match.group(5)) if date_match.group(5) else now.minute
            # If month > current month and no year specified, assume previous year
            if not date_match.group(3) and month > now.month:
                year = now.year - 1
            return datetime(year, month, day, hour, minute)
        except ValueError:
            pass

    # 5. Match relative time expressions
    for pattern, calculator in _TIME_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            try:
                return calculator(match, now)
            except Exception:
                pass

    return now if fallback_to_now else None


def is_within_days(
    post_time: datetime | None,
    days: int = 30,
    reference_time: datetime | None = None,
    grace_hours: int = 48,
) -> bool:
    """Check if post_time is within the last `days` days.

    Args:
        post_time: Parsed datetime of the post. If None, returns False.
        days: Maximum age in days (default: 30 days for 1 month).
        reference_time: Reference datetime (default: now).
        grace_hours: Small grace period in hours (default: 48 hours) to safely accommodate
            posts marked as "1 tháng" or border dates without premature cutoff.
    """
    if post_time is None:
        return False
    now = reference_time or datetime.now()
    cutoff = now - timedelta(days=days, hours=grace_hours)
    return post_time >= cutoff


def is_within_hours(
    post_time: datetime | None,
    hours: float = 3.0,
    reference_time: datetime | None = None,
    grace_minutes: int = 15,
) -> bool:
    """Check if post_time is within the last `hours` hours."""
    if post_time is None:
        return False
    now = reference_time or datetime.now()
    cutoff = now - timedelta(hours=hours, minutes=grace_minutes)
    return post_time >= cutoff


def is_within_time_window(
    post_time: datetime | None,
    hours: float | None = None,
    days: float | None = None,
    reference_time: datetime | None = None,
) -> bool:
    """Check if post_time satisfies specified hours or days freshness limit."""
    if post_time is None:
        return False
    if hours is not None and hours > 0:
        return is_within_hours(post_time, hours=hours, reference_time=reference_time)
    if days is not None and days > 0:
        return is_within_days(post_time, days=int(days), reference_time=reference_time)
    return True
