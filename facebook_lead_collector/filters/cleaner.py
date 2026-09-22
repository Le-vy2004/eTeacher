"""Data cleaning, normalization, and entity extraction module for eTeacher."""
import re
from typing import NamedTuple

# Mappings for common letter-for-digit anti-scraping obfuscations in FB posts
_LETTER_DIGIT_MAP = str.maketrans({
    'o': '0', 'O': '0',
    'i': '1', 'I': '1', 'l': '1', 'L': '1',
})


class ExtractedLeadInfo(NamedTuple):
    """Structured fields extracted from raw post text."""

    phone: str | None
    zalo_url: str | None
    min_budget: int | None
    max_budget: int | None
    budget_unit: str | None
    subject: str
    grade: str
    lead_type: str


def extract_phone(text: str) -> str | None:
    """Extract and normalize a 10-digit Vietnamese phone number from raw text.

    Handles common obfuscations: spaces, dots, dashes, parentheses, letter substitution (o->0, I->1).
    """
    if not text:
        return None

    # Step 1: Normalize letter substitutions commonly used to hide phone numbers
    normalized = text.translate(_LETTER_DIGIT_MAP)

    # Step 2: Match potential 10-digit VN phone patterns (starts with 03, 05, 07, 08, 09, +84)
    # Supports parentheses around prefix e.g. (098) 765-4321
    pattern = r'(?:(?:\+84|84|0|\(0|\(\+84)[35789]\d?\)?)(?:[\s\.\-]*\d){7,8}'
    match = re.search(pattern, normalized)

    if match:
        raw_num = match.group(0)
        # Strip non-digits
        digits = re.sub(r'\D', '', raw_num)
        if digits.startswith('84'):
            digits = '0' + digits[2:]
        if len(digits) == 10 and digits.startswith('0'):
            return digits

    return None


def generate_zalo_url(phone: str | None) -> str | None:
    """Generate a direct 1-click Zalo chat URL for a given phone number."""
    if not phone:
        return None
    return f"https://zalo.me/{phone}"


def parse_budget(text: str) -> tuple[int | None, int | None, str | None]:
    """Parse budget/tutor fee into min_budget, max_budget, and budget_unit.

    Supports:
        "300k/buổi" -> (300000, 300000, "buổi")
        "300.000đ/buổi" -> (300000, 300000, "buổi")
        "250.000 VNĐ" -> (250000, 250000, None)
        "2tr5/tháng" -> (2500000, 2500000, "tháng")
        "150-200k/h" -> (150000, 200000, "giờ")
        "200.000 - 300.000đ" -> (200000, 300000, None)
        "2.5tr/tháng" -> (2500000, 2500000, "tháng")
    """
    if not text:
        return None, None, None

    clean_text = text.lower()

    # Determine unit
    unit = None
    if re.search(r'/(?:b|buổi|buoi)\b', clean_text) or 'buổi' in clean_text or 'buoi' in clean_text:
        unit = "buổi"
    elif re.search(r'/(?:h|giờ|gio|tiếng|tieng)\b', clean_text) or 'giờ' in clean_text or 'tiếng' in clean_text:
        unit = "giờ"
    elif re.search(r'/(?:tháng|thang|t)\b', clean_text) or 'tháng' in clean_text or 'thang' in clean_text:
        unit = "tháng"

    # Pattern 1: Range with k / tr / triệu
    range_pattern = r'(\d+(?:[\.,]\d+)?)\s*(k|tr|triệu|trieu)?\s*[\-\~àa]\s*(\d+(?:[\.,]\d+)?)\s*(k|tr|triệu|trieu)'
    match_range = re.search(range_pattern, clean_text)
    if match_range:
        v1_str, unit1, v2_str, unit2 = match_range.groups()
        unit_final = unit2 or unit1 or 'k'
        mult = 1_000_000 if unit_final in ('tr', 'triệu', 'trieu') else 1_000
        mult1 = 1_000_000 if unit1 in ('tr', 'triệu', 'trieu') else mult
        try:
            v1 = int(float(v1_str.replace(',', '.')) * mult1)
            v2 = int(float(v2_str.replace(',', '.')) * mult)
            return min(v1, v2), max(v1, v2), unit
        except ValueError:
            pass

    # Pattern 2: Range with full numbers and explicit currency: 200.000 - 300.000đ
    vnd_range_pattern = r'(\d{1,3}(?:[\.,]\d{3})+)\s*(?:đ|vnd|vnđ)?\s*[\-\~àa]\s*(\d{1,3}(?:[\.,]\d{3})+)\s*(?:đ|vnd|vnđ)?'
    m_vnd_range = re.search(vnd_range_pattern, clean_text)
    if m_vnd_range:
        v1_s, v2_s = m_vnd_range.groups()
        try:
            v1 = int(re.sub(r'\D', '', v1_s))
            v2 = int(re.sub(r'\D', '', v2_s))
            if v1 < 50_000_000 and v2 < 50_000_000:
                return min(v1, v2), max(v1, v2), unit
        except ValueError:
            pass

    # Pattern 3: Vietnamese slang e.g. 2tr5, 1tr8, 3tr2
    slang_pattern = r'(\d+)\s*(tr|triệu|trieu)\s*(\d+)\b'
    m_slang = re.search(slang_pattern, clean_text)
    if m_slang:
        d1, _, d2 = m_slang.groups()
        try:
            fraction = float('0.' + d2)
            val = int((int(d1) + fraction) * 1_000_000)
            return val, val, unit
        except ValueError:
            pass

    # Pattern 4: Single value with explicit k / tr / triệu (300k, 2.5 triệu, 2tr)
    single_pattern = r'(\d+(?:[\.,]\d+)?)\s*(k|tr|triệu|trieu)\b'
    match_single = re.search(single_pattern, clean_text)
    if match_single:
        v_str, u_str = match_single.groups()
        mult = 1_000_000 if u_str in ('tr', 'triệu', 'trieu') else 1_000
        try:
            val = int(float(v_str.replace(',', '.')) * mult)
            return val, val, unit
        except ValueError:
            pass

    # Pattern 5: Full numbers with explicit currency or unit: 300.000đ, 250,000 VNĐ, 300.000/buổi
    full_pattern = r'(?:học phí|lương|giá|chi phí)?\s*(\d{1,3}(?:[\.,]\d{3})+)\s*(đ|vnd|vnđ|/buổi|/b|/h|/tháng)\b'
    m_full = re.search(full_pattern, clean_text)
    if m_full:
        try:
            val = int(re.sub(r'\D', '', m_full.group(1)))
            if val < 50_000_000:
                return val, val, unit
        except ValueError:
            pass

    # Pattern 6: Fallback for 'học phí: 300.000' without explicit currency symbol
    hp_pattern = r'(?:học phí|lương|giá)\s*:?\s*(\d{1,3}(?:[\.,]\d{3})+)\b'
    m_hp = re.search(hp_pattern, clean_text)
    if m_hp:
        try:
            val = int(re.sub(r'\D', '', m_hp.group(1)))
            if val < 50_000_000:
                return val, val, unit
        except ValueError:
            pass

    return None, None, unit


def extract_subject_and_grade(text: str) -> tuple[str, str]:
    """Extract standardized subject and grade taxonomy from post text."""
    if not text:
        return "Khác", "Khác"

    t_lower = text.lower()

    # Subjects detection
    subject = "Khác"
    if re.search(r'\b(tiếng việt|tieng viet)\b', t_lower):
        subject = "Tiếng Việt"
    elif re.search(r'\b(toán|math|gia sư toán)\b', t_lower):
        subject = "Toán"
    elif re.search(r'\b(lý|vật lý|physics)\b', t_lower):
        subject = "Vật Lý"
    elif re.search(r'\b(hóa|hóa học|chemistry)\b', t_lower):
        subject = "Hóa Học"
    elif re.search(r'\b(tiếng anh|english|ielts|toeic|anh văn)\b', t_lower):
        subject = "Ngoại Ngữ (Tiếng Anh)"
    elif re.search(r'\b(văn|ngữ văn|literativity)\b', t_lower):
        subject = "Ngữ Văn"
    elif re.search(r'\b(sinh|sinh học|biology)\b', t_lower):
        subject = "Sinh Học"
    elif re.search(r'\b(khtn|khoa học tự nhiên)\b', t_lower):
        subject = "Khoa Học Tự Nhiên (KHTN)"
    elif re.search(r'\b(khxh|khoa học xã hội)\b', t_lower):
        subject = "Khoa Học Xã Hội (KHXH)"
    elif re.search(r'\b(sử|lịch sử)\b', t_lower):
        subject = "Lịch Sử"
    elif re.search(r'\b(địa|địa lý|dia ly)\b', t_lower):
        subject = "Địa Lý"
    elif re.search(r'\b(tin|tin học|lập trình|python|pascal|scratch)\b', t_lower):
        subject = "Tin Học"
    elif re.search(r'\b(tiểu học|cấp 1|rèn chữ|tập đọc)\b', t_lower):
        subject = "Tiểu Học"
    elif re.search(r'\b(tiếng trung|tiếng nhật|tiếng hàn|trung|nhat|han)\b', t_lower):
        subject = "Ngoại Ngữ Khác"

    # Grade detection
    grade = "Khác"
    # Specific exam prep prioritized before general grade numbers
    if re.search(r'\b(luyện thi đại học|ôn thi đại học|đại học|thpt quốc gia|luyện thi 12|ôn thi 12)\b', t_lower):
        grade = "Luyện Thi ĐH"
    elif re.search(r'\b(luyện thi vào 10|ôn thi vào 10|thi vào 10|vào 10|ôn thi cấp 3|luyện thi cấp 3)\b', t_lower):
        grade = "Luyện Thi Vào 10"
    elif re.search(r'\b(tiền tiểu học|chuẩn bị vào lớp 1|chuẩn bị lên lớp 1|mầm non|mẫu giáo)\b', t_lower):
        grade = "Tiền Tiểu Học"
    else:
        for g_num in range(12, 0, -1):
            if re.search(rf'\blớp\s*{g_num}\b|\bl{g_num}\b', t_lower):
                grade = f"Lớp {g_num}"
                break

    if grade == "Khác":
        if re.search(r'\b(tiểu học|cấp 1)\b', t_lower):
            grade = "Tiểu Học (Lớp 1-5)"
        elif re.search(r'\b(thcs|cấp 2)\b', t_lower):
            grade = "THCS (Lớp 6-9)"
        elif re.search(r'\b(thpt|cấp 3)\b', t_lower):
            grade = "THPT (Lớp 10-12)"

    return subject, grade


def classify_lead_type(text: str, author: str | None = None) -> str:
    """Classify post into 'Phụ huynh / Học sinh', 'Trung tâm / Môi giới', or 'Gia sư nhận lớp'."""
    if not text:
        return "Khác"

    t_lower = text.lower()

    # Tutor self-promotion seeking students (Supply - must be excluded)
    tutor_supply_patterns = [
        r'\b(em nhận dạy|em là sinh viên|sinh viên sư phạm|nhận dạy kèm|mình nhận dạy|chào mọi người em là)\b',
        r'\b(nhận dạy|nhận kèm|em có nhận kèm|mình có nhận kèm|em có dạy|mình có dạy|em là gia sư|mình là gia sư|tôi là gia sư)\b',
        r'\b(tuyển sinh|chiêu sinh|nhận học viên|tuyển học viên|khai giảng|mở lớp|khóa học)\b',
        r'\b(mình dạy kèm|em dạy kèm|học thử miễn phí|học thử free|được học thử|có học thử|đăng ký học thử)\b',
        r'\b(người mất gốc|dành cho người mất gốc|lấy lại căn bản|lấy lại gốc|chiêu sinh khóa học|lấy lại kiến thức)\b',
        r'\b(chỉ từ\s*\d+|1 kèm 1 chỉ từ|1-1 chỉ từ|học phí chỉ|học phí từ\s*\d+)\b',
        r'\b(không cần học nhóm|ko cần học nhóm|k cần học nhóm)\b',
        r'\b(phụ huynh quan tâm inbox cô|phụ huynh quan tâm ib em|ba mẹ quan tâm ib|bố mẹ quan tâm ib)\b',
        r'\b(liên hệ cô để đăng ký|liên hệ thầy để đăng ký|ib cô để học|inbox cô để học)\b',
    ]
    for tp in tutor_supply_patterns:
        if re.search(tp, t_lower):
            return "Gia sư nhận lớp"

    # Center recruiting tutors (Trung tâm cần tuyển gia sư / giao lớp)
    if re.search(r'\b(phí\s*\d+%\s*|mã lớp|mã số lớp|trung tâm|giao lớp|phí nhận lớp|phí giao lớp|suất\s*\d+|thu nhập:\s*\d+k|ca làm:\s*\d+h|tuyển gia sư|tuyển dụng gia sư)\b', t_lower):
        return "Trung tâm / Môi giới"

    # Direct seeker indicators (Parents / Students)
    if re.search(r'\b(cần tìm gia sư|cần gia sư|tìm gia sư|cần tìm|phụ huynh cần|tìm bạn dạy kèm|cần sinh viên dạy|tìm sinh viên dạy|gia sư cho bé|gia sư cho con|mẹ cần tìm|bố cần tìm|ba cần tìm|mình là phụ huynh)\b', t_lower):
        return "Phụ huynh / Học sinh"

    return "Cần tuyển gia sư"


def clean_and_extract_lead_info(content: str, author: str | None = None) -> ExtractedLeadInfo:
    """Full extraction pipeline for raw post content."""
    phone = extract_phone(content)
    zalo_url = generate_zalo_url(phone)
    min_b, max_b, unit = parse_budget(content)
    subj, gr = extract_subject_and_grade(content)
    l_type = classify_lead_type(content, author=author)

    return ExtractedLeadInfo(
        phone=phone,
        zalo_url=zalo_url,
        min_budget=min_b,
        max_budget=max_b,
        budget_unit=unit,
        subject=subj,
        grade=gr,
        lead_type=l_type,
    )
