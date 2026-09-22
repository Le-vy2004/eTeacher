"""Self-check unit test for data cleaning and extraction engine."""
import sys
from pathlib import Path

# Ensure project root is in sys.path and auto-inject .venv if needed
project_dir = Path(__file__).resolve().parent.parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

try:
    import dotenv
except ImportError:
    venv_sites = list(project_dir.glob(".venv/lib/python*/site-packages"))
    if venv_sites:
        sys.path.insert(0, str(venv_sites[0]))

from filters.cleaner import (
    classify_lead_type,
    clean_and_extract_lead_info,
    extract_phone,
    extract_subject_and_grade,
    generate_zalo_url,
    parse_budget,
)


def test_phone_extraction():
    assert extract_phone("Cần gia sư Toán 12, SĐT: 0987.654.321") == "0987654321"
    assert extract_phone("Liên hệ o981234567 nhé") == "0981234567"
    assert extract_phone("SĐT 098 123 4567 (Zalo)") == "0981234567"
    assert extract_phone("LH Zalo: (098) 765-4321") == "0987654321"
    assert extract_phone("SĐT (090) 123 4567") == "0901234567"
    assert extract_phone("Không có SĐT ở đây") is None
    print("✓ Phone extraction tests passed!")


def test_zalo_url_generation():
    assert generate_zalo_url("0987654321") == "https://zalo.me/0987654321"
    assert generate_zalo_url(None) is None
    print("✓ Zalo URL generation tests passed!")


def test_budget_parsing():
    min_b, max_b, unit = parse_budget("Học phí 300k/buổi 2 tiếng")
    assert min_b == 300000 and max_b == 300000 and unit == "buổi"

    min_b, max_b, unit = parse_budget("Lương 150-200k/h")
    assert min_b == 150000 and max_b == 200000 and unit == "giờ"

    min_b, max_b, unit = parse_budget("Ngân sách 2.5tr/tháng")
    assert min_b == 2500000 and max_b == 2500000 and unit == "tháng"

    min_b, max_b, unit = parse_budget("Học phí 300.000đ/buổi, liên hệ Zalo 0987654321")
    assert min_b == 300000 and max_b == 300000 and unit == "buổi"

    min_b, max_b, unit = parse_budget("Lương 250.000 VNĐ/buổi")
    assert min_b == 250000 and max_b == 250000 and unit == "buổi"

    min_b, max_b, unit = parse_budget("Học phí 2tr5/tháng")
    assert min_b == 2500000 and max_b == 2500000 and unit == "tháng"

    min_b, max_b, unit = parse_budget("Học phí 200.000 - 300.000đ")
    assert min_b == 200000 and max_b == 300000
    print("✓ Budget parsing tests passed!")


def test_subject_and_grade_extraction():
    subj, gr = extract_subject_and_grade("Cần gia sư dạy Toán lớp 12 ôn thi ĐH")
    assert subj == "Toán"
    assert gr == "Lớp 12"

    subj, gr = extract_subject_and_grade("Tìm giáo viên Tiếng Anh IELTS cấp 3")
    assert subj == "Ngoại Ngữ (Tiếng Anh)"
    assert gr == "THPT (Lớp 10-12)"

    subj, gr = extract_subject_and_grade("Cần gia sư Tiếng Việt lớp 3 rèn chữ")
    assert subj == "Tiếng Việt"
    assert gr == "Lớp 3"

    subj, gr = extract_subject_and_grade("Cần gia sư ôn thi vào 10 môn Toán Văn")
    assert subj == "Toán"
    assert gr == "Luyện Thi Vào 10"

    subj, gr = extract_subject_and_grade("Gia sư dạy KHTN lớp 7")
    assert subj == "Khoa Học Tự Nhiên (KHTN)"
    assert gr == "Lớp 7"

    subj, gr = extract_subject_and_grade("Cần gia sư cho bé chuẩn bị vào lớp 1")
    assert gr == "Tiền Tiểu Học"
    print("✓ Subject and grade extraction tests passed!")


def test_classification():
    assert classify_lead_type("Mã lớp 1024: Gia sư Toán lớp 10, phí 30%") == "Trung tâm / Môi giới"
    assert classify_lead_type("Phụ huynh cần tìm gia sư Văn lớp 9") == "Phụ huynh / Học sinh"
    assert classify_lead_type("Em là sinh viên Bách Khoa nhận dạy kèm Lý") == "Gia sư nhận lớp"
    print("✓ Lead classification tests passed!")


def main():

    test_phone_extraction()
    test_zalo_url_generation()
    test_budget_parsing()
    test_subject_and_grade_extraction()
    test_classification()
    print("\n🎉 ALL CLEANER TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
