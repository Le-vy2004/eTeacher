"""Keyword filtering for Facebook posts seeking tutors."""
from pathlib import Path
import sys
import unicodedata

# Ensure project root is in sys.path when running directly
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from utils.text_utils import normalize_text

DEFAULT_KEYWORDS: list[str] = [
    "tìm gia sư",
    "cần gia sư",
    "tuyển gia sư",
    "cần tìm gia sư",
    "tìm giáo viên",
    "cần giáo viên",
    "tuyển giáo viên",
    "gia sư dạy kèm",
    "dạy kèm",
    "tìm người dạy kèm",
    "cần người dạy kèm",
    "nhận lớp dạy kèm",
    "gia sư toán",
    "gia sư tiếng anh",
    "gia sư tiếng Anh",
    "gia sư lý",
    "gia sư hóa",
    "gia sư văn",
    "gia sư sinh",
    "gia sư tiểu học",
    "gia sư cấp 1",
    "gia sư cấp 2",
    "gia sư cấp 3",
    "gia sư online",
    "gia sư tại nhà",
    "dạy toán",
    "dạy tiếng anh",
    "dạy tiếng Anh",
    "dạy kèm tại nhà",
]


def find_matching_keywords(
    text: str | None,
    keywords: list[str] | None = None,
) -> list[str]:
    """Find all matching keywords in post content.

    Characteristics:
    - Case-insensitive matching.
    - Handles redundant whitespaces and linebreaks.
    - Supports Vietnamese Unicode (NFC normalized).
    - Can return multiple keywords if post matches more than one.
    - Deduplicates case-variants (e.g., 'gia sư tiếng anh' vs 'gia sư tiếng Anh').
    - Returns empty list [] if no matches found.

    Args:
        text: Post content to analyze.
        keywords: Optional custom list of keywords (defaults to DEFAULT_KEYWORDS).

    Returns:
        List of matched keyword strings.
    """
    if not text:
        return []

    # Normalize text to NFC, single spaces, lowercase
    cleaned_text = normalize_text(text).lower()
    if not cleaned_text:
        return []

    target_keywords = keywords if keywords is not None else DEFAULT_KEYWORDS

    matched: list[str] = []
    seen_lower: set[str] = set()

    for kw in target_keywords:
        normalized_kw = normalize_text(kw)
        lower_kw = normalized_kw.lower()

        if not lower_kw or lower_kw in seen_lower:
            continue

        # Check if lowercase keyword exists in lowercase cleaned text
        if lower_kw in cleaned_text:
            matched.append(normalized_kw)
            seen_lower.add(lower_kw)

    return matched


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    test_samples = [
        "Phụ huynh cần tìm gia sư toán lớp 8 tại Quận 7.",
        "CẦN GIA SƯ TIẾNG ANH ôn thi chứng chỉ IELTS",
        "Thanh lý bộ bàn ghế học sinh giá rẻ",
        "Gia đình đang cần giáo viên dạy kèm gia sư lý và hóa",
    ]

    print("\n--- Kiểm Tra Bộ Lọc Keyword Filter ---")
    for sample in test_samples:
        matches = find_matching_keywords(sample)
        print(f"Nội dung: \"{sample}\"")
        print(f"-> Khớp từ khóa: {matches if matches else '[Không khớp]'}\n")
