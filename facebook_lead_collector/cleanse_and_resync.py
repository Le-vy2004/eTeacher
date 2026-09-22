"""Utility script to cleanse existing database and resync pure parent leads to Google Sheets."""
import shutil
import sqlite3
from pathlib import Path
import sys

project_dir = Path(__file__).resolve().parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

from database.sqlite_db import get_all_leads
from filters.cleaner import classify_lead_type
from filters.keyword_filter import is_suspicious_author, is_tutor_or_broker_post
from sheets.google_sheets import GoogleSheetsClient, SHEET_HEADERS
from utils.logger import logger


def main():
    db_file = project_dir / "data" / "leads.db"
    backup_file = project_dir / "data" / "leads.db.bak"

    if db_file.exists():
        shutil.copy2(db_file, backup_file)
        logger.info(f"Database backed up to '{backup_file}'")

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    rows = cursor.execute("SELECT id, author, content FROM leads").fetchall()
    logger.info(f"Loaded {len(rows)} records from SQLite database.")

    to_delete_ids = []
    for lid, author, content in rows:
        if is_tutor_or_broker_post(content, author=author) or classify_lead_type(content, author=author) != "Phụ huynh / Học sinh":
            to_delete_ids.append(lid)

    logger.info(f"Found {len(to_delete_ids)} broker / tutor supply leads to remove.")
    if to_delete_ids:
        cursor.executemany("DELETE FROM leads WHERE id = ?", [(i,) for i in to_delete_ids])
        conn.commit()
        logger.info(f"Deleted {len(to_delete_ids)} invalid records. Vacuuming database...")
        conn.execute("VACUUM")
        conn.commit()

    conn.close()

    # Fetch remaining verified parent leads
    verified_leads = get_all_leads(db_path=db_file)
    logger.info(f"Remaining verified parent/student leads: {len(verified_leads)}")

    # Resync to Google Sheets
    sheets_client = GoogleSheetsClient()
    if sheets_client.connect():
        logger.info("Clearing and updating Google Sheets with cleansed data...")
        try:
            sheets_client.worksheet.clear()
            sheets_client.worksheet.update([SHEET_HEADERS], "A1:M1")
            sheets_client._known_urls.clear()
            if verified_leads:
                appended = sheets_client.append_leads(verified_leads)
                logger.info(f"Successfully synced {appended} verified leads to Google Sheets!")
        except Exception as e:
            logger.error(f"Error resyncing to Google Sheets: {e}")

    print("\n✅ CLEANSE AND RESYNC COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
