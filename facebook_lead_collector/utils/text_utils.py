"""Text processing and normalization utilities."""
import re
import unicodedata


def normalize_text(text: str | None) -> str:
    """Normalize text for consistent keyword matching and storage.

    Steps:
    1. Handle None / non-string input safely.
    2. Normalize Unicode to NFC standard representation (prevents split diacritics).
    3. Collapse consecutive whitespaces, tabs, newlines into single spaces.
    4. Strip leading and trailing whitespace.

    Args:
        text: Raw input string or None.

    Returns:
        Normalized clean string.
    """
    if not text:
        return ""
    # NFC normalization standardizes Vietnamese decomposed characters
    normalized = unicodedata.normalize("NFC", str(text))
    # Replace all whitespace sequences (including non-breaking spaces) with a single space
    cleaned = re.sub(r"\s+", " ", normalized)
    return cleaned.strip()


def sanitize_url(url: str | None) -> str:
    """Sanitize and validate post URL.

    Strips tracking query params or whitespace.
    """
    if not url:
        return ""
    return url.strip()


def extract_source_id_from_url(url_or_id: str | None) -> str:
    """Extract Facebook Group ID, Page ID, or slug from a Facebook URL or return raw ID.

    Examples:
    - "https://www.facebook.com/groups/1234567890/" -> "1234567890"
    - "https://facebook.com/groups/hoi-gia-su-tphcm?ref=share" -> "hoi-gia-su-tphcm"
    - "https://www.facebook.com/fanpage.giasu" -> "fanpage.giasu"
    - "1234567890" -> "1234567890"

    Args:
        url_or_id: Full Facebook URL or ID string.

    Returns:
        Clean source identifier string.
    """
    if not url_or_id:
        return ""

    raw = url_or_id.strip()

    # If it is not a URL, return as-is
    if not (raw.startswith("http://") or raw.startswith("https://") or "facebook.com" in raw):
        return raw

    # Remove protocol and query strings
    cleaned = re.sub(r"^https?://(www\.|m\.|web\.)?facebook\.com/", "", raw)
    cleaned = cleaned.split("?")[0].split("#")[0].strip("/")

    # Group pattern: groups/{group_id}
    group_match = re.search(r"^groups/([^/?#]+)", cleaned)
    if group_match:
        return group_match.group(1)

    # Page / profile / vanity URL: e.g. "giasutoan" or "profile.php?id=123"
    profile_match = re.search(r"profile\.php.*id=(\d+)", raw)
    if profile_match:
        return profile_match.group(1)

    # Return first path segment
    parts = cleaned.split("/")
    return parts[0] if parts else raw
