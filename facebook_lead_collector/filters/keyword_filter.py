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
    "dạy kèm tại nhà",
    "gia sư tphcm",
    "gia sư hồ chí minh",
    "gia sư sài gòn",
    "gia sư hà nội",
    "tìm gia sư tphcm",
    "tìm gia sư thành phố hồ chí minh",
    "tìm gia sư sài gòn",
    "cần gia sư tphcm",
]

# Từ khóa loại trừ (Spam / Bài tuyển dụng bán hàng, phục vụ, việc làm khác)
NEGATIVE_KEYWORDS: list[str] = [
    "tuyển nhân viên",
    "bán quần áo",
    "bán hàng",
    "bán thời gian",
    "phục vụ",
    "bảo vệ",
    "tuyển thợ",
    "thanh lý",
    "cho thuê nhà",
    "cho thuê phòng",
    "tuyển tạp vụ",
    "nhân viên phục vụ",
    "giao hàng",
    "tuyển telesale",
]

def find_matching_keywords(
    text: str | None,
    keywords: list[str] | None = None,
) -> list[str]:
    """Find all matching keywords in post content with negative keyword filtering.

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

    # Check negative keywords first (Loại bỏ các bài tuyển dụng bán quần áo, tạp vụ...)
    has_tutor_intent = any(core in cleaned_text for core in ["gia sư", "dạy kèm", "lớp dạy", "tìm giáo viên", "cần giáo viên"])
    for neg_kw in NEGATIVE_KEYWORDS:
        if neg_kw in cleaned_text and not has_tutor_intent:
            return []

    target_keywords = keywords if keywords is not None else DEFAULT_KEYWORDS

    matched: list[str] = []
    seen_lower: set[str] = set()

    for kw in target_keywords:
        normalized_kw = normalize_text(kw)
        lower_kw = normalized_kw.lower()

        # Bỏ qua các địa danh đứng một mình (hcm, tphcm, hà nội) nếu không đi kèm gia sư
        if lower_kw in ["hcm", "tphcm", "hồ chí minh", "thành phố hồ chí minh", "hà nội", "sài gòn"]:
            continue

        if not lower_kw or lower_kw in seen_lower:
            continue

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

    test_text = "TUYỂN NHÂN VIÊN NỮ BÁN QUẦN ÁO tại Tân Phú TP.HCM"
    print("Test tuyển bán quần áo:", find_matching_keywords(test_text))
    
    tutor_text = "Cần tìm gia sư dạy tiếng anh tại nhà cho bé khu vực kim chung đông anh"
    print("Test bài gia sư thật:", find_matching_keywords(tutor_text))
