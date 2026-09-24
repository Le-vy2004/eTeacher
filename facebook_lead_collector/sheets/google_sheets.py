"""Google Sheets integration client for Facebook Lead Collector."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

# Ensure project root is in sys.path when running this file directly from an IDE
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

for venv_path in (_project_root / ".venv", _project_root.parent / ".venv"):
    sites = list(venv_path.glob("lib/python*/site-packages"))
    if sites:
        if str(sites[0]) not in sys.path:
            sys.path.insert(0, str(sites[0]))
        break

from config import get_settings
from models.post import Lead
from utils.logger import logger

SHEET_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

SHEET_HEADERS = [
    "💬 Chat Zalo Direct",
    "Số Điện Thoại",
    "Môn Học",
    "Khối Lớp",
    "Ngân Sách (VND)",
    "🔗 Link Bài FB",
    "Tên Người Đăng",
    "Thời Gian Đăng",
    "Nội Dung Bài Đăng",
    "Nhóm Facebook",
    "Từ Khóa",
    "Thời Gian Thu Thập",
    "Phân Loại",
    "Trạng Thái Kết Bạn",
    "Thời Gian Kết Bạn",
]


class GoogleSheetsClient:
    """Client for synchronizing tutoring leads into Google Sheets."""

    def __init__(
        self,
        credentials_file: str | Path | None = None,
        sheet_name: str | None = None,
        worksheet_name: str | None = None,
    ):
        settings = get_settings()
        self.credentials_path = (
            Path(credentials_file)
            if credentials_file
            else settings.resolved_google_credentials_path
        )
        self.sheet_name = sheet_name or settings.google_sheet_name
        self.worksheet_name = worksheet_name or settings.google_worksheet_name

        self.gc: gspread.Client | None = None
        self.spreadsheet: gspread.Spreadsheet | None = None
        self.worksheet: gspread.Worksheet | None = None
        self.is_connected: bool = False
        self._known_urls: set[str] = set()

    def connect(self) -> bool:
        """Authenticate with Google Service Account and connect to sheet.

        Returns:
            True if connection succeeded, False otherwise.
        """
        if not self.credentials_path.is_file():
            logger.warning(
                f"Google credentials file not found at: {self.credentials_path}. "
                "Google Sheets synchronization will be disabled."
            )
            self.is_connected = False
            return False

        try:
            import gspread
            from google.oauth2.service_account import Credentials

            logger.info("Connecting to Google Sheets API...")
            credentials = Credentials.from_service_account_file(
                str(self.credentials_path),
                scopes=SHEET_SCOPES,
            )
            self.gc = gspread.authorize(credentials)

            # Open spreadsheet by title
            try:
                self.spreadsheet = self.gc.open(self.sheet_name)
            except gspread.SpreadsheetNotFound:
                logger.error(
                    f"Spreadsheet '{self.sheet_name}' not found. "
                    "Please create the Google Sheet and share edit access with "
                    f"the service account email in '{self.credentials_path}'."
                )
                self.is_connected = False
                return False

            # Open or create worksheet
            try:
                self.worksheet = self.spreadsheet.worksheet(self.worksheet_name)
            except gspread.WorksheetNotFound:
                worksheets = self.spreadsheet.worksheets()
                if len(worksheets) == 1 and not worksheets[0].row_values(1):
                    self.worksheet = worksheets[0]
                    try:
                        self.worksheet.update_title(self.worksheet_name)
                    except Exception:
                        pass
                else:
                    logger.info(
                        f"Worksheet '{self.worksheet_name}' not found. Creating it..."
                    )
                    self.worksheet = self.spreadsheet.add_worksheet(
                        title=self.worksheet_name, rows="1000", cols="15"
                    )

            # Check and initialize headers if empty or outdated
            headers = self.worksheet.row_values(1)
            if not headers:
                logger.info("Sheet header is empty. Initializing column headers...")
                self.worksheet.update([SHEET_HEADERS], "A1:O1")
            elif headers != SHEET_HEADERS:
                logger.info("Updating worksheet headers to match required column structure...")
                self.worksheet.update([SHEET_HEADERS], "A1:O1")

            # Pre-cache existing post URLs to prevent duplicate writes
            self._load_existing_urls()

            self.is_connected = True
            logger.info(
                f"Connected to Google Sheet: '{self.sheet_name}' -> '{self.worksheet_name}' "
                f"({len(self._known_urls)} existing leads cached)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}", exc_info=True)
            self.is_connected = False
            return False

    def _load_existing_urls(self) -> None:
        """Cache existing post URLs from sheet to prevent duplicate rows."""
        self._known_urls.clear()
        if not self.worksheet:
            return

        try:
            import re
            url_col_letter = "F"
            headers = self.worksheet.row_values(1)
            if headers:
                for idx, h in enumerate(headers):
                    if h in ("🔗 Link Bài FB", "Link bài viết", "Post URL"):
                        url_col_letter = chr(ord("A") + idx)
                        break

            col_formulas = self.worksheet.get(f"{url_col_letter}2:{url_col_letter}", value_render_option="FORMULA")
            for row in col_formulas:
                if row:
                    val = str(row[0])
                    m = re.search(r'https?://[^\s",;)]+', val)
                    if m:
                        self._known_urls.add(m.group(0).strip())
                    elif val.startswith("http"):
                        self._known_urls.add(val.strip())
        except Exception as e:
            logger.warning(f"Could not preload existing URLs from sheet: {e}")

    def post_exists(self, post_url: str) -> bool:
        """Check if post URL already exists in Google Sheet.

        Args:
            post_url: The post URL to check.

        Returns:
            True if post URL is already present in sheet, False otherwise.
        """
        if not post_url:
            return False
        clean_url = post_url.strip()
        return clean_url in self._known_urls

    def append_lead(self, lead: Lead) -> bool:
        """Append a lead row to the Google Sheet if it does not already exist.

        Args:
            lead: Lead instance to append.

        Returns:
            True if row was appended, False if duplicate or failed.
        """
        if not self.is_connected or not self.worksheet:
            logger.debug("Google Sheets client is not connected; skipping append.")
            return False

        if self.post_exists(lead.post_url):
            logger.debug(f"Lead already exists on Google Sheet: {lead.post_url}")
            return False

        try:
            row_data = lead.to_sheet_row()
            all_vals = self.worksheet.get_all_values()
            next_row = len(all_vals) + 1
            if next_row == 1:
                self.worksheet.update([SHEET_HEADERS], "A1:O1")
                next_row = 2

            if next_row > self.worksheet.row_count:
                self.worksheet.add_rows(50)

            self.worksheet.update([row_data], f"A{next_row}", value_input_option="USER_ENTERED")
            self._known_urls.add(lead.post_url.strip())
            logger.debug(f"Appended lead to Google Sheets at row {next_row}: {lead.post_url}")
            return True
        except Exception as e:
            logger.error(f"Error appending lead to Google Sheets ({lead.post_url}): {e}")
            return False

    def append_leads(self, leads: list[Lead]) -> int:
        """Append multiple leads in batch to Google Sheets.

        Args:
            leads: List of Lead instances to append.

        Returns:
            Number of newly appended leads.
        """
        if not self.is_connected or not self.worksheet:
            logger.debug("Google Sheets client is not connected; skipping batch append.")
            return 0

        rows_to_append = []
        new_leads = []
        for lead in leads:
            if not self.post_exists(lead.post_url):
                rows_to_append.append(lead.to_sheet_row())
                new_leads.append(lead)

        if not rows_to_append:
            return 0

        try:
            all_vals = self.worksheet.get_all_values()
            next_row = len(all_vals) + 1
            if next_row == 1:
                self.worksheet.update([SHEET_HEADERS], "A1:O1")
                next_row = 2

            needed_rows = next_row + len(rows_to_append) - 1
            current_row_count = self.worksheet.row_count
            if needed_rows > current_row_count:
                self.worksheet.add_rows(max(100, needed_rows - current_row_count + 50))

            target_range = f"A{next_row}"
            self.worksheet.update(rows_to_append, target_range, value_input_option="USER_ENTERED")
            for lead in new_leads:
                self._known_urls.add(lead.post_url.strip())
            logger.info(f"Appended {len(rows_to_append)} leads to Google Sheets starting at row {next_row}.")
            return len(rows_to_append)
        except Exception as e:
            logger.error(f"Error appending batch of leads to Google Sheets: {e}")
            return 0

    def update_friend_status(
        self,
        row_number: int,
        status: str,
        requested_at: str | None = None,
    ) -> bool:
        """Update friend request status and timestamp in Google Sheets for a specific row."""
        if not self.is_connected or not self.worksheet:
            return False
        try:
            from datetime import datetime
            ts = requested_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cell_range = f"N{row_number}:O{row_number}"
            self.worksheet.update([[status, ts]], cell_range)
            return True
        except Exception as e:
            logger.error(f"Error updating friend status at row {row_number}: {e}")
            return False

    def get_leads_to_friend(self, limit: int = 50) -> list[dict]:
        """Fetch leads from Google Sheets that need a friend request sent."""
        if not self.is_connected or not self.worksheet:
            return []
        try:
            import re
            raw_formulas = self.worksheet.get("A2:O", value_render_option="FORMULA")
            if not raw_formulas:
                return []

            results = []
            for idx, row in enumerate(raw_formulas, start=2):
                if len(results) >= limit:
                    break

                # Column F (index 5) is Link Bài FB
                raw_link = row[5] if len(row) > 5 else ""
                url_match = re.search(r'https?://[^\s",;)]+', raw_link)
                post_url = url_match.group(0) if url_match else raw_link.strip()

                if not post_url or not post_url.startswith("http"):
                    continue

                # Column G (index 6) is Tên Người Đăng
                author = row[6].strip() if len(row) > 6 else ""

                # Column N (index 13) is Trạng Thái Kết Bạn
                friend_status = row[13].strip() if len(row) > 13 else ""

                # Skip if already processed successfully or marked as anonymous
                if friend_status in (
                    "Đã gửi kết bạn",
                    "Đã là bạn bè",
                    "Đã gửi trước đó",
                    "Tài khoản ẩn danh (Bỏ qua)",
                ):
                    continue

                results.append({
                    "row_number": idx,
                    "post_url": post_url,
                    "author": author,
                    "friend_status": friend_status,
                })

            return results
        except Exception as e:
            logger.error(f"Error retrieving leads to friend from Google Sheets: {e}")
            return []




if __name__ == "__main__":
    # Configure UTF-8 for Windows consoles
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("\n--- Kiểm Tra Kết Nối Google Sheets Client ---")
    client = GoogleSheetsClient()
    print(f"File credentials: {client.credentials_path}")
    print(f"Trạng thái file credentials: {'ĐÃ TÌM THẤY' if client.credentials_path.is_file() else 'CHƯA CÓ'}")
    print(f"Tên Sheet: {client.sheet_name} | Worksheet: {client.worksheet_name}")

    if client.credentials_path.is_file():
        connected = client.connect()
        if connected:
            print("[✓] Kết nối Google Sheets thành công!")
        else:
            print("[X] Kết nối thất bại. Vui lòng kiểm tra quyền chia sẻ bảng tính cho email Service Account.")
    else:
        print("\n[INFO] Chưa cấu hình service_account.json.")
        print("Để chạy thử nghiệm toàn bộ hệ thống bằng dữ liệu giả lập (Mock mode) mà không cần Google Sheet:")
        print("   -> Chạy lệnh: python main.py --mock\n")
