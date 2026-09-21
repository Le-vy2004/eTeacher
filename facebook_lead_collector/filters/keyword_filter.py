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

# Từ khóa gia sư tự ứng tuyển / chào mời nhận lớp (Supply Leads - Phải loại bỏ)
TUTOR_SUPPLY_KEYWORDS: list[str] = [
    "nhận gia sư",
    "nhận dạy kèm",
    "nhận dạy 1-1",
    "nhận dạy các môn",
    "nhận dạy tại nhà",
    "nhận dạy online",
    "em nhận dạy",
    "mình nhận dạy",
    "cô nhận dạy",
    "thầy nhận dạy",
    "bên em nhận",
    "bên mình nhận",
    "cháu nhận dạy",
    "muốn nhận dạy",
    "muốn nhận kèm",
    "muốn nhận dạy kèm",
    "dạ hiện con nhận",
    "đang là sinh viên",
    "hiện là sinh viên",
    "hiện tại đang là sinh viên",
    "sinh viên năm",
    "đang học đại học",
    "sinh viên nhận",
    "giáo viên nhận",
    "góc tìm học sinh",
    "góc tìm kiếm học sinh",
    "trống các buổi",
    "trống lịch",
    "rảnh lịch",
    "rảnh các buổi",
    "rảnh các tối",
    "rảnh tối",
    "trình độ học vấn",
    "thành tích học tập",
    "profile gia sư",
    "cv gia sư",
    "em có kinh nghiệm",
    "mình có kinh nghiệm",
    "phụ huynh nào cần",
    "phụ huynh/học sinh nào cần",
    "học sinh nào cần",
    "ai cần gia sư",
    "bạn nào cần gia sư",
    "anh/chị nào cần gia sư",
    "lớp học online 1 kèm 1",
    "em nhận gia sư",
    "mình nhận gia sư",
    "các bạn gia sư",
    "kèm riêng theo",
]

# Từ khóa rác / Tuyển dụng ngành khác
SPAM_NEGATIVE_KEYWORDS: list[str] = [
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
    "nhóm công khai",
    "thành viên",
    "chỉ báo trạng thái online",
    "đang hoạt động",
]

NEGATIVE_KEYWORDS: list[str] = TUTOR_SUPPLY_KEYWORDS + SPAM_NEGATIVE_KEYWORDS

# Từ khóa thể hiện nhu cầu tìm gia sư từ phía Phụ huynh / Học sinh (Demand Intent)
EXPLICIT_DEMAND_KEYWORDS: list[str] = [
    "tìm gia sư",
    "cần gia sư",
    "tuyển gia sư",
    "cần tìm gia sư",
    "tìm giáo viên",
    "cần giáo viên",
    "tuyển giáo viên",
    "tìm người dạy kèm",
    "cần người dạy kèm",
    "tìm dạy kèm",
    "cần dạy kèm",
    "tìm gia sư tphcm",
    "tìm gia sư hà nội",
    "cần gia sư tphcm",
    "cần gia sư hà nội",
    "gia sư cho bé",
    "gia sư cho con",
    "cần sinh viên dạy",
    "tìm sinh viên dạy",
]


def find_matching_keywords(
    text: str | None,
    keywords: list[str] | None = None,
) -> list[str]:
    """Find all matching keywords in post content with strict demand filtering.

    Filters out tutor self-promotion, advertisements, and spam posts unconditionally.
    Requires clear demand intent (parent or student looking for a tutor).

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

    # 1. Reject negative keywords unconditionally (gia sư tự quảng cáo, bài rác)
    for neg_kw in NEGATIVE_KEYWORDS:
        if neg_kw in cleaned_text:
            return []

    # 2. Demand intent check: Must express seeking a tutor (tìm / cần / tuyển / cho bé / cho con)
    has_demand_intent = any(dk in cleaned_text for dk in EXPLICIT_DEMAND_KEYWORDS) or (
        any(verb in cleaned_text for verb in ["tìm", "cần", "tuyển", "cho bé", "cho con", "cho cháu", "cho em"])
        and any(core in cleaned_text for core in ["gia sư", "dạy kèm", "dạy toán", "dạy tiếng anh", "dạy lý", "dạy hóa", "dạy văn"])
    )

    if not has_demand_intent:
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

    test_spam = "TUYỂN NHÂN VIÊN NỮ BÁN QUẦN ÁO tại Tân Phú TP.HCM"
    print("Test tuyển bán quần áo (loại bỏ):", find_matching_keywords(test_spam))

    test_tutor_ad = "Cháu/em/mình hiện tại đang là sinh viên Đại học Bách Khoa, đang nhận gia sư các môn KHTN..."
    print("Test bài gia sư tự ứng tuyển (loại bỏ):", find_matching_keywords(test_tutor_ad))

    test_real_parent = "Cần tìm gia sư dạy tiếng anh tại nhà cho bé khu vực kim chung đông anh"
    print("Test bài phụ huynh thật (giữ lại):", find_matching_keywords(test_real_parent))

