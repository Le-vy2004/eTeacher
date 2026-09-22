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

from database.sqlite_db import filter_new_post_urls, get_all_leads, init_db, insert_lead, insert_leads_batch
from models.post import Lead


def test_sqlite_batch_operations():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = Path(tmp_db.name)

    try:
        init_db(db_path=db_path)

        # 1. Test batch filter with empty DB
        urls = [
            f"https://www.facebook.com/groups/test/posts/{i}/"
            for i in range(1, 21)
        ]
        new_urls = filter_new_post_urls(urls, db_path=db_path)
        assert len(new_urls) == 20

        # 2. Insert one lead manually
        lead1 = Lead(
            group_name="Group 1",
            keyword="tìm gia sư",
            author="Author 1",
            post_time=datetime.now(),
            post_url=urls[0],
            content="Cần gia sư Toán 10",
        )
        assert insert_lead(lead1, db_path=db_path) is True

        # 3. Filter again: should have 19 new URLs
        filtered = filter_new_post_urls(urls, db_path=db_path)
        assert len(filtered) == 19
        assert urls[0] not in filtered

        # 4. Batch insert remaining 19 leads
        batch_leads = [
            Lead(
                group_name="Group 1",
                keyword="tìm gia sư",
                author=f"Author {i}",
                post_time=datetime.now(),
                post_url=urls[i - 1],
                content=f"Cần gia sư Lý lớp {i % 12 + 1}",
            )
            for i in range(2, 21)
        ]
        inserted_count = insert_leads_batch(batch_leads, db_path=db_path)
        assert inserted_count == 19

        # 5. Filter again: all 20 should now exist
        final_filtered = filter_new_post_urls(urls, db_path=db_path)
        assert len(final_filtered) == 0

        all_leads = get_all_leads(db_path=db_path)
        assert len(all_leads) == 20

        print("✓ SQLite batch operations test passed successfully!")

    finally:
        if db_path.exists():
            db_path.unlink()


if __name__ == "__main__":
    test_sqlite_batch_operations()
