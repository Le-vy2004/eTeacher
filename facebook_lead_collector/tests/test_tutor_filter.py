"""Tests for filtering tutor posts: captures all recruitment/search posts while excluding tutor self-promotion."""
import sys
from pathlib import Path

project_dir = Path(__file__).resolve().parent.parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

from filters.cleaner import classify_lead_type
from filters.keyword_filter import find_matching_keywords


def test_filter_tutor_self_promotion_seeking_students():
    # Bài gia sư tự mở lớp tuyển sinh / tìm học viên (PHẢI LOẠI BỎ)
    ad1 = "Mình dạy kèm tiếng Anh 1 kèm 1 online có học thử miễn phí để đăng ký học thử"
    assert find_matching_keywords(ad1, author="Cô Ngọc Hà") == []
    assert classify_lead_type(ad1) == "Gia sư nhận lớp"

    ad2 = "Em là sinh viên sư phạm nhận dạy kèm môn Toán tại nhà, ai cần gia sư liên hệ mình nhé"
    assert find_matching_keywords(ad2, author="Sinh Viên A") == []
    assert classify_lead_type(ad2) == "Gia sư nhận lớp"


def test_keep_all_tutor_recruitment_posts():
    # Bài trung tâm / cá nhân cần tuyển gia sư (PHẢI GIỮ LẠI ĐẦY ĐỦ THEO YÊU CẦU)
    ad_recruitment1 = "TUYỂN GIA SƯ TIẾNG ANH ONLINE. Thu nhập: 50k – 120k/giờ. Ca làm: 16h – 22h. Dạy online tại nhà"
    matched1 = find_matching_keywords(ad_recruitment1, author="Huỳnh Nhi - Việc Làm Gia Sư Online")
    assert len(matched1) > 0
    assert classify_lead_type(ad_recruitment1) == "Trung tâm / Môi giới"

    ad_recruitment2 = "TÌM GIA SƯ DẠY KÈM TẠI NHÀ. Mã lớp 1024: YC GS nữ dạy Toán lớp 12, phí nhận lớp 35%"
    matched2 = find_matching_keywords(ad_recruitment2, author="Gia Sư Hồng Oanh")
    assert len(matched2) > 0
    assert classify_lead_type(ad_recruitment2) == "Trung tâm / Môi giới"

    ad_recruitment3 = "Mình đang cần gia sư dạy Toán lớp 12. Buổi tối T2, T5. Nhận lớp trực tiếp từ trung tâm, không thu phí nhận lớp."
    matched3 = find_matching_keywords(ad_recruitment3, author="Ma'am Amy")
    assert len(matched3) > 0


def test_keep_real_parent_demand_posts():
    # Bài phụ huynh thật (PHẢI GIỮ LẠI)
    p1 = "Mình đang cần tìm gia sư dạy toán cho 2 bạn lớp 5 và lớp 7. Yêu cầu là gia sư nữ, khu vực Thanh Xuân. Bạn nào dạy được liên hệ mình nhé."
    matched1 = find_matching_keywords(p1, author="Thư Nam")
    assert len(matched1) > 0
    assert classify_lead_type(p1, author="Thư Nam") == "Phụ huynh / Học sinh"

    p2 = "Cần tìm gia sư dạy kèm tiếng Anh tại nhà cho bé lớp 3 khu vực Cầu Giấy, 0912345678."
    matched2 = find_matching_keywords(p2, author="Huong Vo")
    assert len(matched2) > 0
    assert classify_lead_type(p2, author="Huong Vo") == "Phụ huynh / Học sinh"
