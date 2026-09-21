"""Google Sheets integration client for Facebook Lead Collector."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

# Ensure project root is in sys.path when running this file directly from an IDE
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import get_settings
from models.post import Lead
from utils.logger import logger

SHEET_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

SHEET_HEADERS = [
    "Group",
    "Keyword",
    "Author",
    "Post Time",
    "Post URL",
    "Collected At",
    "Content",
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
                        title=self.worksheet_name, rows="1000", cols="10"
                    )

            # Check and initialize headers if empty
            headers = self.worksheet.row_values(1)
            if not headers:
                logger.info("Sheet header is empty. Initializing column headers...")
                self.worksheet.append_row(SHEET_HEADERS)
            elif headers != SHEET_HEADERS:
                logger.warning(
                    f"Worksheet headers differ from expected format.\n"
                    f"Found: {headers}\nExpected: {SHEET_HEADERS}"
                )

            # Pre-cache existing post URLs from column 5 to prevent duplicate writes
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
        """Cache existing post URLs from column 5 (Post URL)."""
        self._known_urls.clear()
        if not self.worksheet:
            return

        try:
            # Column 5 is 'Post URL'
            col_values = self.worksheet.col_values(5)
            # Skip row 1 (header)
            urls = [url.strip() for url in col_values[1:] if url and url.strip()]
            self._known_urls.update(urls)
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
            self.worksheet.append_row(row_data, value_input_option="USER_ENTERED")
            self._known_urls.add(lead.post_url.strip())
            logger.debug(f"Appended lead to Google Sheets: {lead.post_url}")
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
        for lead in leads:
            if not self.post_exists(lead.post_url):
                rows_to_append.append(lead.to_sheet_row())
                self._known_urls.add(lead.post_url.strip())

        if not rows_to_append:
            return 0

        try:
            self.worksheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            logger.info(f"Appended {len(rows_to_append)} leads to Google Sheets.")
            return len(rows_to_append)
        except Exception as e:
            logger.error(f"Error appending batch of leads to Google Sheets: {e}")
            return 0



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
