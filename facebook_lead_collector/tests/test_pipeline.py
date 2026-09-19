"""Pipeline integration tests."""
from datetime import datetime
from pathlib import Path
import pytest

from database.sqlite_db import get_all_leads, init_db
from main import process_posts, run
from models.post import FacebookPost, Lead


@pytest.fixture
def clean_db(tmp_path: Path) -> Path:
    """Fixture providing a fresh temporary SQLite database."""
    db_file = tmp_path / "pipeline_test.db"
    init_db(db_file)
    return db_file


def test_pipeline_with_exact_5_posts(clean_db: Path):
    """Test required scenario:

    5 posts:
    - 2 matching tutor posts
    - 1 duplicate post (matching content, identical post_url)
    - 2 non-matching posts
    Expected: Exactly 2 new leads created.
    """
    now = datetime(2026, 9, 18, 12, 0)

    posts = [
        # 1. Matching post 1
        FacebookPost(
            post_id="p1",
            group_name="Group Test",
            content="Phụ huynh cần tìm gia sư toán lớp 10",
            author="Phụ huynh A",
            post_time=now,
            post_url="https://facebook.com/groups/test/posts/101",
        ),
        # 2. Matching post 2
        FacebookPost(
            post_id="p2",
            group_name="Group Test",
            content="Em đang cần gia sư tiếng anh giao tiếp",
            author="Học sinh B",
            post_time=now,
            post_url="https://facebook.com/groups/test/posts/102",
        ),
        # 3. Duplicate post (same url as post 1)
        FacebookPost(
            post_id="p3",
            group_name="Group Test",
            content="Phụ huynh cần tìm gia sư toán lớp 10 (đăng lại)",
            author="Phụ huynh A",
            post_time=now,
            post_url="https://facebook.com/groups/test/posts/101",
        ),
        # 4. Non-matching post 1
        FacebookPost(
            post_id="p4",
            group_name="Group Test",
            content="Hôm nay thời tiết Hà Nội mát mẻ",
            author="Người dùng C",
            post_time=now,
            post_url="https://facebook.com/groups/test/posts/104",
        ),
        # 5. Non-matching post 2
        FacebookPost(
            post_id="p5",
            group_name="Group Test",
            content="Thanh lý laptop cũ cấu hình cao",
            author="Người dùng D",
            post_time=now,
            post_url="https://facebook.com/groups/test/posts/105",
        ),
    ]

    # Process posts through the pipeline
    stats = process_posts(posts, db_path=clean_db, sheets_client=None)

    # Verifications
    assert stats.collected_count == 5
    assert stats.matched_count == 3  # posts 1, 2, 3 have matching keywords
    assert stats.duplicate_count == 1  # post 3 is a duplicate url
    assert stats.new_leads_count == 2  # exactly 2 new leads created!
    assert stats.error_count == 0

    # Verify leads in SQLite database
    stored_leads = get_all_leads(clean_db)
    assert len(stored_leads) == 2

    urls = {l.post_url for l in stored_leads}
    assert "https://facebook.com/groups/test/posts/101" in urls
    assert "https://facebook.com/groups/test/posts/102" in urls


def test_pipeline_subsequent_run_deduplication(clean_db: Path):
    """Running the pipeline again with the same posts should produce 0 new leads."""
    post = FacebookPost(
        post_id="single_p1",
        group_name="Group Test",
        content="Tìm gia sư hóa lớp 12",
        author="User X",
        post_time=datetime.now(),
        post_url="https://facebook.com/groups/test/posts/999",
    )

    first_stats = process_posts([post], db_path=clean_db)
    assert first_stats.new_leads_count == 1
    assert first_stats.duplicate_count == 0

    # Second run with same post
    second_stats = process_posts([post], db_path=clean_db)
    assert second_stats.new_leads_count == 0
    assert second_stats.duplicate_count == 1


def test_pipeline_handles_empty_content_gracefully(clean_db: Path):
    """Posts with empty or whitespace content should be skipped cleanly."""
    empty_post = FacebookPost(
        post_id="empty_p1",
        group_name="Group Test",
        content="   ",
        author="User Y",
        post_time=datetime.now(),
        post_url="https://facebook.com/groups/test/posts/empty",
    )
    stats = process_posts([empty_post], db_path=clean_db)
    assert stats.collected_count == 1
    assert stats.matched_count == 0
    assert stats.new_leads_count == 0
    assert stats.error_count == 0


def test_run_function_with_mock_collector(tmp_path: Path):
    """Test full run() invocation in mock mode."""
    test_db = tmp_path / "mock_run.db"
    stats = run(
        source_id="test_mock_group",
        mock=True,
        limit=8,
        db_path=test_db,
        enable_sheets=False,
    )
    assert stats.collected_count == 8
    assert stats.new_leads_count > 0
    assert stats.error_count == 0
