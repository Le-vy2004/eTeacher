"""Keyword filtering for Facebook posts seeking or recruiting tutors.

Collects ALL posts that recruit or seek tutors (Parents, Students, and Centers needing tutors).
Excludes ONLY posts where tutors self-promote to recruit students or course advertisements.
"""
from pathlib import Path
import re
import sys

# Ensure project root is in sys.path when running directly
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from utils.text_utils import normalize_text

DEFAULT_KEYWORDS: list[str] = [
    "tuyển gia sư",
    "cần tuyển gia sư",
    "tuyển dụng gia sư",
    "tuyển giáo viên",
    "tìm gia sư",
    "cần gia sư",
    "cần tìm gia sư",
    "tìm gia sư dạy kèm",
    "cần gia sư dạy kèm",
    "tìm người dạy kèm",
    "cần người dạy kèm",
    "tìm người dạy",
    "cần người dạy",
    "tìm bạn dạy kèm",
    "cần bạn dạy kèm",
    "tìm sinh viên dạy",
    "cần sinh viên dạy",
    "tuyển sinh viên dạy",
    "gia sư cho bé",
    "gia sư cho con",
    "gia sư cho cháu",
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
    "dạy kèm tại nhà",
    "gia sư online",
    "gia sư tại nhà",
    "mã lớp",
    "tìm gia sư tphcm",
    "cần gia sư tphcm",
    "tìm gia sư hà nội",
    "cần gia sư hà nội",
    "tìm gia sư đà nẵng",
    "cần gia sư đà nẵng",
]

# Từ khóa gia sư / giáo viên tự chào mời đi tìm học sinh, mở lớp chiêu sinh (Tutor Supply - Cần loại bỏ)
TUTOR_SUPPLY_KEYWORDS: list[str] = [
    # Tuyển sinh / Chiêu sinh / Gom học viên (Không phải tuyển gia sư)
    "tuyển sinh",
    "chiêu sinh",
    "nhận học viên",
    "tuyển học viên",
    "nhận thêm học viên",
    "nhận thêm học sinh",
    "đang nhận thêm học viên",
    "đang nhận thêm học sinh",
    "có lớp giao tiếp",
    "luyện ielts",
    "ôn chứng chỉ",
    "kèm học sinh lớp",
    "khai giảng",
    "mở lớp",
    # Gia sư tự chào mời nhận dạy kèm / tìm học sinh
    "nhận dạy",
    "nhận kèm",
    "nhận gia sư",
    "em có nhận dạy",
    "mình có nhận dạy",
    "em có dạy",
    "mình có dạy",
    "em có nhận kèm",
    "mình có nhận kèm",
    "em là gia sư",
    "mình là gia sư",
    "tôi là gia sư",
    "em có lớp",
    "mình có lớp",
    "lớp nhóm nhỏ",
    "chỉ từ",
    "1 kèm 1 chỉ từ",
    "1-1 chỉ từ",
    "học phí từ",
    "học phí chỉ",
    "không cần học nhóm",
    "ko cần học nhóm",
    "k cần học nhóm",
    "học thử free",
    "học thử miễn phí",
    "buổi học thử",
    "đăng ký học thử",
    "chuyên lấy lại kiến thức",
    "lấy lại kiến thức cho học viên",
    "lấy lại gốc cho học viên",
    # Tự giới thiệu đi dạy / tìm học trò
    "nhận gia sư",
    "nhận dạy kèm",
    "nhận dạy 1-1",
    "nhận dạy 1 kèm 1",
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
    "profile gia sư",
    "cv gia sư",
    "em có kinh nghiệm đi dạy",
    "mình có kinh nghiệm đi dạy",
    "phụ huynh nào cần gia sư liên hệ",
    "học sinh nào cần liên hệ",
    "ai cần gia sư liên hệ",
    "bạn nào cần gia sư liên hệ",
    "anh/chị nào cần gia sư liên hệ",
    "em nhận gia sư",
    "mình nhận gia sư",
    # Mở lớp chiêu sinh / học thử
    "mình dạy kèm",
    "em dạy kèm",
    "học thử miễn phí",
    "học thử 1 buổi",
    "học thử 2 buổi",
    "được học thử",
    "có học thử",
    "đăng ký học thử",
    "inbox để đăng ký học",
    "ib để đăng ký học",
    "người mất gốc",
    "dành cho người mất gốc",
    "lấy lại căn bản",
    "lấy lại gốc",
    "chiêu sinh khóa học",
    "khai giảng khóa học",
    "phụ huynh quan tâm inbox cô",
    "phụ huynh quan tâm ib em",
    "ba mẹ quan tâm ib",
    "bố mẹ quan tâm ib",
    "liên hệ cô để đăng ký",
    "liên hệ thầy để đăng ký",
    "ib cô để học",
    "không cần gia sư",
    "ko cần gia sư",
    "k cần gia sư",
]

# Từ khóa bài rác / tuyển dụng ngành khác hoàn toàn / Header giới thiệu nhóm
SPAM_NEGATIVE_KEYWORDS: list[str] = [
    "nhóm công khai",
    "nhóm riêng tư",
    "quy tắc nhóm",
    "thành viên",
    "k thành viên",
    "tuyển nhân viên bán hàng",
    "bán quần áo",
    "bán hàng online",
    "bán thời gian quán",
    "phục vụ quán",
    "bảo vệ",
    "tuyển thợ",
    "thanh lý đồ",
    "cho thuê nhà",
    "cho thuê phòng",
    "tuyển tạp vụ",
    "nhân viên phục vụ",
    "giao hàng shopee",
    "tuyển telesale",
    "chỉ báo trạng thái online",
    "đang hoạt động",
]

NEGATIVE_KEYWORDS: list[str] = TUTOR_SUPPLY_KEYWORDS + SPAM_NEGATIVE_KEYWORDS

TUTOR_SUPPLY_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(?:cô|thầy|em|mình|cháu)\s+đang\s+nhận\s+(?:thêm\s+)?(?:học\s+viên|học\s+sinh|lớp|dạy)\b", re.IGNORECASE),
    re.compile(r"\bnhận\s+thêm\s+(?:học\s+viên|học\s+sinh|lớp)\b", re.IGNORECASE),
    re.compile(r"\b(?:có\s+lớp\s+giao\s+tiếp|luyện\s+ielts|ôn\s+chứng\s+chỉ)\b", re.IGNORECASE),
    re.compile(r"\bchuyên\s+(?:nhận\s+dạy|lấy\s+lại\s+gốc|kèm\s+1[- ]1)\b", re.IGNORECASE),
]

# Từ khóa thể hiện nhu cầu TUYỂN / TÌM GIA SƯ
EXPLICIT_DEMAND_KEYWORDS: list[str] = [
    "tuyển gia sư",
    "cần tuyển gia sư",
    "tuyển dụng gia sư",
    "tuyển giáo viên",
    "tuyển sinh viên dạy",
    "tìm gia sư",
    "cần gia sư",
    "cần tìm gia sư",
    "tìm người dạy kèm",
    "cần người dạy kèm",
    "tìm dạy kèm",
    "cần dạy kèm",
    "tìm gia sư tphcm",
    "tìm gia sư bình thạnh",
    "cần gia sư tphcm",
    "cần gia sư bình thạnh",
    "gia sư cho bé",
    "gia sư cho con",
    "gia sư cho cháu",
    "cần sinh viên dạy",
    "tìm sinh viên dạy",
    "tìm bạn dạy",
    "cần bạn dạy",
    "mình là phụ huynh",
    "phụ huynh cần tìm",
    "mẹ cần tìm gia sư",
    "ba cần tìm gia sư",
    "bố cần tìm gia sư",
]


def is_suspicious_author(author: str | None) -> bool:
    """Always return False because tutor recruitment posts from centers and coordinators are desired leads."""
    return False


def is_tutor_or_broker_post(text: str, author: str | None = None) -> bool:
    """Return True ONLY if post is a tutor self-promotion seeking students or non-tutoring spam."""
    if not text:
        return False
    cleaned_text = normalize_text(text).lower()
    if any(neg in cleaned_text for neg in NEGATIVE_KEYWORDS):
        return True
    if any(p.search(cleaned_text) for p in TUTOR_SUPPLY_PATTERNS):
        return True
    return False


def find_matching_keywords(
    text: str | None,
    author: str | None = None,
    keywords: list[str] | None = None,
) -> list[str]:
    """Find all matching tutor recruitment / search keywords in post content.

    Captures all posts seeking or recruiting tutors (Parents, Students, and Center Coordinators).
    Filters out ONLY tutor self-promotion (tutors looking for students) and spam.

    Args:
        text: Post content to analyze.
        author: Optional author name.
        keywords: Optional custom list of keywords (defaults to DEFAULT_KEYWORDS).

    Returns:
        List of matched keyword strings.
    """
    if not text:
        return []

    cleaned_text = normalize_text(text).lower()
    if not cleaned_text:
        return []

    # 1. Reject pure tutor self-promotion seeking students or off-topic spam
    for neg_kw in NEGATIVE_KEYWORDS:
        if neg_kw in cleaned_text:
            return []
    for pattern in TUTOR_SUPPLY_PATTERNS:
        if pattern.search(cleaned_text):
            return []

    # 2. Demand intent check: Must express seeking or recruiting a tutor
    demand_matches = [dk for dk in EXPLICIT_DEMAND_KEYWORDS if dk in cleaned_text]
    has_demand_intent = bool(demand_matches)

    if not has_demand_intent:
        return []

    target_keywords = keywords if keywords is not None else DEFAULT_KEYWORDS

    matched: list[str] = []
    seen_lower: set[str] = set()

    for kw in target_keywords:
        normalized_kw = normalize_text(kw)
        lower_kw = normalized_kw.lower()

        if lower_kw in ["hcm", "tphcm", "hồ chí minh", "thành phố hồ chí minh", "hà nội", "sài gòn", "đà nẵng"]:
            continue

        if not lower_kw or lower_kw in seen_lower:
            continue

        if lower_kw in cleaned_text:
            matched.append(normalized_kw)
            seen_lower.add(lower_kw)

    # If no target keyword matched but explicit demand phrases exist, use the matched demand phrases
    if not matched and demand_matches:
        matched.extend(demand_matches[:2])

    return matched
