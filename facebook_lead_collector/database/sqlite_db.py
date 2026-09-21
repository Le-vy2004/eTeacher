"""SQLite database storage and deduplication for tutoring leads."""
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
from typing import Sequence

# Ensure project root is in sys.path when running directly
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config import get_settings
from models.post import Lead
from utils.logger import logger

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL,
    keyword TEXT NOT NULL,
    author TEXT,
    post_time TEXT,
    post_url TEXT NOT NULL UNIQUE,
    content TEXT,
    collected_at TEXT NOT NULL
);
"""


def _resolve_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve database path, ensuring parent directory exists."""
    if db_path is None:
        target = get_settings().resolved_database_path
    else:
        target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Get a SQLite database connection with row factory enabled."""
    path = _resolve_db_path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path | None = None) -> None:
    """Initialize database tables and indexes if they do not exist.

    Args:
        db_path: Optional custom path to database file.
    """
    path = _resolve_db_path(db_path)
    try:
        with get_connection(path) as conn:
            conn.executescript(SCHEMA_SQL)
            # Automatic schema migration for content column if database already existed
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(leads)")
            existing_columns = {row["name"] for row in cursor.fetchall()}
            if "content" not in existing_columns:
                cursor.execute("ALTER TABLE leads ADD COLUMN content TEXT")
                conn.commit()
                logger.info("Migrated SQLite schema: added 'content' column to leads table.")
        logger.info(f"Database initialized successfully at {path}")
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database at {path}: {e}")
        raise


def lead_exists(post_url: str, db_path: str | Path | None = None) -> bool:
    """Check if a lead with given post_url already exists in the database.

    Args:
        post_url: Post URL to check.
        db_path: Optional custom path to database file.

    Returns:
        True if post_url is already recorded, False otherwise.
    """
    if not post_url:
        return False
    path = _resolve_db_path(db_path)
    try:
        with get_connection(path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM leads WHERE post_url = ? LIMIT 1", (post_url,))
            return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"Error checking lead existence for URL {post_url}: {e}")
        return False


def insert_lead(lead: Lead, db_path: str | Path | None = None) -> bool:
    """Insert a new lead into SQLite database.

    If post_url already exists (due to UNIQUE constraint), insertion is ignored
    and returns False.

    Args:
        lead: Lead instance to insert.
        db_path: Optional custom path to database file.

    Returns:
        True if inserted successfully, False if duplicate or failed.
    """
    path = _resolve_db_path(db_path)
    insert_sql = """
    INSERT INTO leads (group_name, keyword, author, post_time, post_url, content, collected_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    try:
        with get_connection(path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                insert_sql,
                (
                    lead.group_name,
                    lead.keyword,
                    lead.author,
                    lead.post_time.isoformat(),
                    lead.post_url,
                    lead.content,
                    lead.collected_at.isoformat(),
                ),
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        # Unique constraint on post_url triggered
        logger.debug(f"Lead already exists (duplicate post_url): {lead.post_url}")
        return False
    except sqlite3.Error as e:
        logger.error(f"Failed to insert lead ({lead.post_url}): {e}")
        return False


def get_all_leads(db_path: str | Path | None = None) -> list[Lead]:
    """Retrieve all leads stored in the database.

    Args:
        db_path: Optional custom path to database file.

    Returns:
        List of Lead model instances ordered by id DESC.
    """
    path = _resolve_db_path(db_path)
    leads: list[Lead] = []
    try:
        with get_connection(path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT group_name, keyword, author, post_time, post_url, content, collected_at FROM leads ORDER BY id DESC"
            )
            for row in cursor.fetchall():
                leads.append(
                    Lead(
                        group_name=row["group_name"],
                        keyword=row["keyword"],
                        author=row["author"] or "Unknown",
                        post_time=datetime.fromisoformat(row["post_time"]),
                        post_url=row["post_url"],
                        content=row["content"] or "" if "content" in row.keys() else "",
                        collected_at=datetime.fromisoformat(row["collected_at"]),
                    )
                )
    except sqlite3.Error as e:
        logger.error(f"Failed to fetch leads from database: {e}")
    return leads


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("\n--- Kiểm Tra Cơ Sở Dữ Liệu SQLite ---")
    settings = get_settings()
    db_path = settings.resolved_database_path
    print(f"Đường dẫn database: {db_path}")
    init_db(db_path)
    leads = get_all_leads(db_path)
    print(f"Tổng số leads đang lưu trữ: {len(leads)}")
    for idx, item in enumerate(leads[:5], 1):
        print(f"  {idx}. [{item.post_time.strftime('%Y-%m-%d %H:%M')}] {item.author} | {item.keyword} | {item.post_url}")
    if len(leads) > 5:
        print(f"  ... và {len(leads) - 5} leads khác.")
    print()
