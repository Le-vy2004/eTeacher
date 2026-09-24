"""Mock test suite for Google Sheets 13-column formatting and batch append."""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

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

from models.post import Lead
from sheets.google_sheets import GoogleSheetsClient, SHEET_HEADERS


def test_sheet_row_13_columns():
    lead = Lead(
        group_name="Hội Gia Sư Hà Nội",
        keyword="cần gia sư, tìm gia sư",
        author="Nguyễn Văn A",
        post_time=datetime(2026, 9, 21, 14, 0, 0),
        post_url="https://www.facebook.com/groups/hoigiasuhanoi/posts/1001/",
        content="Cần gia sư dạy Toán lớp 12 tại Cầu Giấy, học phí 300k/buổi. SĐT: 0987654321",
        phone="0987654321",
        zalo_url="https://zalo.me/0987654321",
        min_budget=300000,
        max_budget=300000,
        budget_unit="buổi",
        subject="Toán",
        grade="Lớp 12",
        lead_type="Phụ huynh / Học sinh",
        collected_at=datetime(2026, 9, 21, 21, 0, 0),
    )

    row = lead.to_sheet_row()
    assert len(row) == 15, f"Expected 15 columns, got {len(row)}"
    assert len(SHEET_HEADERS) == 15

    # Column A: Zalo Direct hyperlink formula
    assert row[0] == '=HYPERLINK("https://zalo.me/0987654321"; "💬 Chat Zalo")'
    # Column B: Phone number
    assert row[1] == "0987654321"
    # Column C: Subject
    assert row[2] == "Toán"
    # Column D: Grade
    assert row[3] == "Lớp 12"
    # Column E: Formatted budget
    assert "300,000" in row[4]
    # Column F: FB Link formula
    assert row[5] == '=HYPERLINK("https://www.facebook.com/groups/hoigiasuhanoi/posts/1001/"; "🔗 Xem bài viết")'
    # Column G: Author
    assert row[6] == "Nguyễn Văn A"
    # Column H: Post time
    assert row[7] == "2026-09-21 14:00:00"
    # Column M: Classification
    assert row[12] == "Phụ huynh / Học sinh"

    print("✓ Lead 13-column formatting matches specification!")


def test_mock_batch_append_leads():
    client = GoogleSheetsClient()
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_values.return_value = [["header1"]]
    mock_worksheet.row_count = 1000
    client.worksheet = mock_worksheet
    client.is_connected = True

    leads = [
        Lead(
            group_name="Group 1",
            keyword="tìm gia sư",
            author=f"Author {i}",
            post_time=datetime.now(),
            post_url=f"https://www.facebook.com/groups/test/posts/{i}/",
            content=f"Cần gia sư Lý lớp {i}",
            phone="0987654321",
            zalo_url="https://zalo.me/0987654321",
        )
        for i in range(1, 11)
    ]

    # Test batch append
    appended = client.append_leads(leads)
    assert appended == 10
    assert mock_worksheet.update.call_count == 1

    # Verify that the call passed all 10 rows with USER_ENTERED option to A2
    call_args = mock_worksheet.update.call_args
    rows_passed = call_args[0][0]
    target_range = call_args[0][1]
    assert len(rows_passed) == 10
    assert target_range == "A2"
    assert call_args[1].get("value_input_option") == "USER_ENTERED"

    # Appending duplicate leads should be filtered out by client cache
    appended_again = client.append_leads(leads)
    assert appended_again == 0
    assert mock_worksheet.update.call_count == 1  # No extra API call made

    print("✓ Google Sheets batch append test passed successfully!")


if __name__ == "__main__":
    test_sheet_row_13_columns()
    test_mock_batch_append_leads()
