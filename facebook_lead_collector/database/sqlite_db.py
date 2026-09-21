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

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_or_id TEXT NOT NULL UNIQUE,
    name TEXT,
    added_at TEXT NOT NULL
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


def load_sources_from_file(sources_file: str | Path | None = None) -> list[str]:
    """Read target Facebook group/page URLs from a text file, ignoring empty lines & comments."""
    if sources_file is None:
        target_path = get_settings().resolved_sources_file_path
    else:
        target_path = Path(sources_file)

    if not target_path.exists():
        logger.warning(f"Sources file not found at '{target_path}'. Creating empty template...")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("# Danh sách các trang/nhóm Facebook cần quét (mỗi dòng 1 URL)\n", encoding="utf-8")
        return []

    sources = []
    with target_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                sources.append(line)

    return sources


def save_source_to_db(url_or_id: str, name: str = "", db_path: str | Path | None = None) -> bool:
    """Save a new group/page source URL into SQLite sources table."""
    if not url_or_id:
        return False
    path = _resolve_db_path(db_path)
    sql = "INSERT INTO sources (url_or_id, name, added_at) VALUES (?, ?, ?)"
    try:
        with get_connection(path) as conn:
            conn.execute(sql, (url_or_id, name, datetime.now().isoformat()))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        logger.error(f"Failed to save source {url_or_id}: {e}")
        return False


def get_sources_from_db(db_path: str | Path | None = None) -> list[str]:
    """Fetch all stored target sources from SQLite database."""
    path = _resolve_db_path(db_path)
    results = []
    try:
        with get_connection(path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url_or_id FROM sources ORDER BY id ASC")
            for row in cursor.fetchall():
                results.append(row["url_or_id"])
    except sqlite3.Error:
        pass
    return results



