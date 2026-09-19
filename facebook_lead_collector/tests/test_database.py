"""Tests for SQLite database storage and deduplication."""
from datetime import datetime
from pathlib import Path
import pytest

from database.sqlite_db import init_db, lead_exists, insert_lead, get_all_leads
from models.post import Lead


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Fixture providing a clean temporary SQLite database."""
    db_file = tmp_path / "test_leads.db"
    init_db(db_file)
    return db_file


def test_init_db_creates_table(temp_db: Path):
    """Verify that init_db creates the leads table and can be queried."""
    assert temp_db.exists()
    assert get_all_leads(temp_db) == []


def test_insert_lead_and_existence(temp_db: Path):
    """Test inserting a valid lead and checking lead_exists."""
    lead = Lead(
        group_name="Hội Gia Sư TPHCM",
        keyword="tìm gia sư, gia sư toán",
        author="Nguyễn Văn A",
        post_time=datetime(2026, 9, 18, 10, 30),
        post_url="https://facebook.com/groups/123/posts/101",
        collected_at=datetime(2026, 9, 18, 11, 0),
    )

    assert not lead_exists(lead.post_url, temp_db)
    inserted = insert_lead(lead, temp_db)
    assert inserted is True
    assert lead_exists(lead.post_url, temp_db)

    # Verify retrieved data matches
    all_leads = get_all_leads(temp_db)
    assert len(all_leads) == 1
    assert all_leads[0].post_url == lead.post_url
    assert all_leads[0].group_name == "Hội Gia Sư TPHCM"
    assert all_leads[0].keyword == "tìm gia sư, gia sư toán"
    assert all_leads[0].author == "Nguyễn Văn A"


def test_duplicate_url_rejected(temp_db: Path):
    """Verify that duplicate post_url cannot be inserted twice."""
    lead1 = Lead(
        group_name="Group A",
        keyword="tìm gia sư",
        author="User 1",
        post_time=datetime.now(),
        post_url="https://facebook.com/posts/dup-01",
    )
    lead2 = Lead(
        group_name="Group B",
        keyword="gia sư tiếng anh",
        author="User 2",
        post_time=datetime.now(),
        post_url="https://facebook.com/posts/dup-01",
    )

    first_insert = insert_lead(lead1, temp_db)
    assert first_insert is True

    second_insert = insert_lead(lead2, temp_db)
    assert second_insert is False

    leads = get_all_leads(temp_db)
    assert len(leads) == 1
    assert leads[0].group_name == "Group A"
