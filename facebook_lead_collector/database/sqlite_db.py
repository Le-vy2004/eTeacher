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
    phone TEXT,
    zalo_url TEXT,
    min_budget INTEGER,
    max_budget INTEGER,
    budget_unit TEXT,
    subject TEXT,
    grade TEXT,
    lead_type TEXT,
    friend_status TEXT,
    friend_requested_at TEXT,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_or_id TEXT NOT NULL UNIQUE,
    name TEXT,
    added_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_post_url ON leads(post_url);
CREATE INDEX IF NOT EXISTS idx_leads_collected_at ON leads(collected_at);
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
    """Initialize database tables and indexes if they do not exist."""
    path = _resolve_db_path(db_path)
    try:
        with get_connection(path) as conn:
            conn.executescript(SCHEMA_SQL)
            # Automatic schema migration for new columns
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(leads)")
            existing_columns = {row["name"] for row in cursor.fetchall()}
            
            new_cols = {
                "content": "TEXT",
                "phone": "TEXT",
                "zalo_url": "TEXT",
                "min_budget": "INTEGER",
                "max_budget": "INTEGER",
                "budget_unit": "TEXT",
                "subject": "TEXT",
                "grade": "TEXT",
                "lead_type": "TEXT",
                "friend_status": "TEXT",
                "friend_requested_at": "TEXT",
            }
            for col_name, col_type in new_cols.items():
                if col_name not in existing_columns:
                    cursor.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Migrated SQLite schema: added '{col_name}' column to leads table.")

            # Ensure indices exist even after migrations
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_post_url ON leads(post_url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_collected_at ON leads(collected_at)")
            conn.commit()
        logger.info(f"Database initialized successfully at {path}")
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database at {path}: {e}")
        raise


def lead_exists(post_url: str, db_path: str | Path | None = None) -> bool:
    """Check if a lead with given post_url already exists in the database."""
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


def filter_new_post_urls(urls: Sequence[str], db_path: str | Path | None = None) -> set[str]:
    """Given a sequence of post URLs, return the set of URLs that do NOT exist in the database."""
    if not urls:
        return set()
    unique_urls = list(dict.fromkeys(u.strip() for u in urls if u and u.strip()))
    if not unique_urls:
        return set()

    path = _resolve_db_path(db_path)
    existing: set[str] = set()
    chunk_size = 400
    try:
        with get_connection(path) as conn:
            cursor = conn.cursor()
            for i in range(0, len(unique_urls), chunk_size):
                chunk = unique_urls[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                cursor.execute(f"SELECT post_url FROM leads WHERE post_url IN ({placeholders})", chunk)
                for row in cursor.fetchall():
                    existing.add(row[0])
    except sqlite3.Error as e:
        logger.error(f"Error filtering post URLs: {e}")
        return set(unique_urls)

    return set(unique_urls) - existing


def insert_lead(lead: Lead, db_path: str | Path | None = None) -> bool:
    """Insert a new lead into SQLite database."""
    path = _resolve_db_path(db_path)
    insert_sql = """
    INSERT INTO leads (
        group_name, keyword, author, post_time, post_url, content,
        phone, zalo_url, min_budget, max_budget, budget_unit, subject, grade, lead_type, collected_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    lead.phone,
                    lead.zalo_url,
                    lead.min_budget,
                    lead.max_budget,
                    lead.budget_unit,
                    lead.subject,
                    lead.grade,
                    lead.lead_type,
                    lead.collected_at.isoformat(),
                ),
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        logger.debug(f"Lead already exists (duplicate post_url): {lead.post_url}")
        return False
    except sqlite3.Error as e:
        logger.error(f"Failed to insert lead ({lead.post_url}): {e}")
        return False


def insert_leads_batch(leads: list[Lead], db_path: str | Path | None = None) -> int:
    """Insert a list of leads in a single batch transaction. Returns number of inserted leads."""
    if not leads:
        return 0
    path = _resolve_db_path(db_path)
    insert_sql = """
    INSERT OR IGNORE INTO leads (
        group_name, keyword, author, post_time, post_url, content,
        phone, zalo_url, min_budget, max_budget, budget_unit, subject, grade, lead_type, collected_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    inserted = 0
    try:
        with get_connection(path) as conn:
            cursor = conn.cursor()
            initial_changes = conn.total_changes
            for lead in leads:
                cursor.execute(
                    insert_sql,
                    (
                        lead.group_name,
                        lead.keyword,
                        lead.author,
                        lead.post_time.isoformat(),
                        lead.post_url,
                        lead.content,
                        lead.phone,
                        lead.zalo_url,
                        lead.min_budget,
                        lead.max_budget,
                        lead.budget_unit,
                        lead.subject,
                        lead.grade,
                        lead.lead_type,
                        lead.collected_at.isoformat(),
                    ),
                )
            conn.commit()
            inserted = conn.total_changes - initial_changes
            return inserted
    except sqlite3.Error as e:
        logger.error(f"Failed to batch insert leads: {e}")
        return inserted


def get_all_leads(db_path: str | Path | None = None) -> list[Lead]:
    """Retrieve all leads stored in the database."""
    path = _resolve_db_path(db_path)
    leads: list[Lead] = []
    try:
        with get_connection(path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM leads ORDER BY id DESC"
            )
            for row in cursor.fetchall():
                row_keys = row.keys()
                leads.append(
                    Lead(
                        group_name=row["group_name"],
                        keyword=row["keyword"],
                        author=row["author"] or "Unknown",
                        post_time=datetime.fromisoformat(row["post_time"]),
                        post_url=row["post_url"],
                        content=row["content"] if "content" in row_keys and row["content"] else "",
                        phone=row["phone"] if "phone" in row_keys else None,
                        zalo_url=row["zalo_url"] if "zalo_url" in row_keys else None,
                        min_budget=row["min_budget"] if "min_budget" in row_keys else None,
                        max_budget=row["max_budget"] if "max_budget" in row_keys else None,
                        budget_unit=row["budget_unit"] if "budget_unit" in row_keys else None,
                        subject=row["subject"] if "subject" in row_keys and row["subject"] else "Khác",
                        grade=row["grade"] if "grade" in row_keys and row["grade"] else "Khác",
                        lead_type=row["lead_type"] if "lead_type" in row_keys and row["lead_type"] else "Phụ huynh / Học sinh",
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
        # Check if singular or plural counterpart exists
        alt_names = [
            target_path.parent / (target_path.stem + "s" + target_path.suffix),
            target_path.parent / (target_path.stem[:-1] + target_path.suffix) if target_path.stem.endswith("s") else None,
        ]
        for alt in alt_names:
            if alt and alt.exists():
                target_path = alt
                break

    if not target_path.exists():
        logger.warning(f"Sources file not found at '{target_path}'. Creating empty template...")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("# Danh sách các trang/nhóm Facebook cần quét (mỗi dòng 1 URL)\n", encoding="utf-8")
        return []

    sources = []
    with target_path.open("r", encoding="utf-8") as f:
        for line in f:
            clean_line = line.split("#")[0].strip()
            if clean_line:
                sources.append(clean_line)

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


def update_lead_friend_status(
    post_url: str,
    status: str,
    requested_at: str | None = None,
    db_path: str | Path | None = None,
) -> bool:
    """Update the friend request status of a lead by post_url."""
    if not post_url:
        return False
    path = _resolve_db_path(db_path)
    ts = requested_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = "UPDATE leads SET friend_status = ?, friend_requested_at = ? WHERE post_url = ?"
    try:
        with get_connection(path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (status, ts, post_url))
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Failed to update friend status for {post_url}: {e}")
        return False


def get_leads_needing_friend_request(
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict]:
    """Get leads that have not yet had a friend request sent or completed."""
    path = _resolve_db_path(db_path)
    results = []
    sql = """
        SELECT id, author, post_url, group_name, content, friend_status, friend_requested_at
        FROM leads
        WHERE friend_status IS NULL 
           OR friend_status NOT IN ('Đã gửi kết bạn', 'Đã là bạn bè', 'Đã gửi trước đó', 'Tài khoản ẩn danh (Bỏ qua)')
        ORDER BY id DESC
        LIMIT ?
    """
    try:
        with get_connection(path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (limit,))
            for row in cursor.fetchall():
                results.append(dict(row))
    except sqlite3.Error as e:
        logger.error(f"Error fetching leads for friend request: {e}")
    return results




