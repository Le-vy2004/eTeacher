"""Integration test for eTeacher end-to-end processing pipeline."""
import sys
import tempfile
from datetime import datetime
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

from database.sqlite_db import get_all_leads, init_db
from main import process_posts
from models.post import FacebookPost


def test_full_pipeline():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = Path(tmp_db.name)

    try:
        init_db(db_path=db_path)

        mock_posts = [
            FacebookPost(
                post_id="post_1",
                group_name="Hội Gia Sư Hà Nội",
                content="Cần gia sư dạy Toán lớp 12 tại Cầu Giấy, học phí 300k/buổi. LH Zalo: 0987.654.321",
                author="Nguyễn Văn A",
                post_time=datetime.now(),
                post_url="https://www.facebook.com/groups/hoigiasuhanoi/posts/1001/",
            ),
            FacebookPost(
                post_id="post_2",
                group_name="Gia Sư Tiếng Anh TPHCM",
                content="Mình cần tìm gia sư Tiếng Anh IELTS lớp 10 cho bé, học phí 250k/buổi. SĐT 0912345678",
                author="Trần Thị B",
                post_time=datetime.now(),
                post_url="https://www.facebook.com/groups/giasutienganh/posts/1002/",
            ),
            FacebookPost(
                post_id="post_3",
                group_name="Gia Sư Tiếng Anh TPHCM",
                content="Mã lớp 999: Cần 1 gia sư Tiếng Anh IELTS lớp 10, phí 30%. SĐT 0912345678",
                author="Trung Tâm Gia Sư XYZ",
                post_time=datetime.now(),
                post_url="https://www.facebook.com/groups/giasutienganh/posts/1003/",
            ),
        ]

        stats = process_posts(mock_posts, db_path=db_path)

        assert stats.collected_count == 3
        assert stats.matched_count == 3
        assert stats.new_leads_count == 3

        all_leads = get_all_leads(db_path=db_path)
        assert len(all_leads) == 3

        # Check lead 1 (Direct Parent)
        lead1 = [l for l in all_leads if "1001" in l.post_url][0]
        assert lead1.phone == "0987654321"
        assert lead1.zalo_url == "https://zalo.me/0987654321"
        assert lead1.subject == "Toán"
        assert lead1.grade == "Lớp 12"
        assert lead1.min_budget == 300000
        assert lead1.lead_type == "Phụ huynh / Học sinh"

        # Check lead 2 (Direct Parent)
        lead2 = [l for l in all_leads if "1002" in l.post_url][0]
        assert lead2.phone == "0912345678"
        assert lead2.subject == "Ngoại Ngữ (Tiếng Anh)"
        assert lead2.grade == "Lớp 10"
        assert lead2.min_budget == 250000

        # Check lead 3 (Tutor recruitment post from Center)
        lead3 = [l for l in all_leads if "1003" in l.post_url][0]
        assert lead3.phone == "0912345678"
        assert lead3.lead_type == "Trung tâm / Môi giới"

        print("✓ Full pipeline integration test passed successfully!")

    finally:
        if db_path.exists():
            db_path.unlink()


if __name__ == "__main__":
    test_full_pipeline()
