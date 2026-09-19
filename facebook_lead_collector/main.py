"""Main entrypoint and pipeline execution for Facebook Lead Collector."""
import argparse
from datetime import datetime
from pathlib import Path
import sys
import time

# Ensure UTF-8 output on Windows consoles to prevent UnicodeEncodeError
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from collectors.base import BaseCollector
from collectors.facebook import FacebookCollector
from collectors.mock import MockFacebookCollector
from config import get_settings
from database.sqlite_db import init_db, insert_lead, lead_exists
from filters.keyword_filter import find_matching_keywords
from models.post import FacebookPost, Lead
from pydantic import BaseModel, Field
from sheets.google_sheets import GoogleSheetsClient
from utils.logger import logger


class PipelineStats(BaseModel):
    """Statistics summary for a pipeline execution run."""

    collected_count: int = 0
    matched_count: int = 0
    duplicate_count: int = 0
    new_leads_count: int = 0
    error_count: int = 0
    new_leads: list[Lead] = Field(default_factory=list)


def process_posts(
    posts: list[FacebookPost],
    db_path: Path | str | None = None,
    sheets_client: GoogleSheetsClient | None = None,
) -> PipelineStats:
    """Process a list of Facebook posts through the lead qualification pipeline.

    Workflow per post:
    1. Extract and validate content.
    2. Match keywords. If no match -> skip.
    3. Check if post_url already exists in SQLite. If exists -> skip as duplicate.
    4. Construct Lead model.
    5. Save to SQLite database.
    6. Save to Google Sheets if connected and not duplicate.

    Args:
        posts: List of FacebookPost objects.
        db_path: Optional custom SQLite database path.
        sheets_client: Optional connected GoogleSheetsClient instance.

    Returns:
        PipelineStats containing summary metrics and list of new leads.
    """
    stats = PipelineStats(collected_count=len(posts))

    for post in posts:
        try:
            # 1. Content extraction
            content = post.content
            if not content or not content.strip():
                continue

            # 2. Keyword matching
            matched_keywords = find_matching_keywords(content)
            if not matched_keywords:
                continue

            stats.matched_count += 1

            # 3. SQLite deduplication check
            if lead_exists(post.post_url, db_path=db_path):
                stats.duplicate_count += 1
                continue

            # 4. Create Lead
            lead = Lead(
                group_name=post.group_name,
                keyword=", ".join(matched_keywords),
                author=post.author,
                post_time=post.post_time,
                post_url=post.post_url,
                collected_at=datetime.now(),
            )

            # 5. Save to SQLite
            saved = insert_lead(lead, db_path=db_path)
            if not saved:
                stats.duplicate_count += 1
                continue

            stats.new_leads_count += 1
            stats.new_leads.append(lead)

            # 6. Save to Google Sheets (if connected)
            if sheets_client and sheets_client.is_connected:
                sheets_client.append_lead(lead)

        except Exception as e:
            stats.error_count += 1
            logger.error(
                f"Error processing post {getattr(post, 'post_id', 'unknown')}: {e}",
                exc_info=True,
            )
            continue

    return stats


def run(
    source_id: str | None = None,
    mock: bool = False,
    limit: int | None = None,
    db_path: Path | str | None = None,
    enable_sheets: bool = True,
    token: str | None = None,
) -> PipelineStats:
    """Execute the full lead collection pipeline once.

    Args:
        source_id: Facebook group/page ID or full URL, or mock source name.
        mock: If True, uses MockFacebookCollector without live API.
        limit: Max number of posts to retrieve.
        db_path: Optional custom SQLite path.
        enable_sheets: Whether to attempt Google Sheets synchronization.
        token: Optional Facebook access token (overrides config).

    Returns:
        PipelineStats with execution results.
    """
    settings = get_settings()
    actual_limit = limit or settings.collector_limit
    effective_source_id = source_id or settings.facebook_source_id or "default_source"

    logger.info("Starting collector")

    # 1. Initialize SQLite Database
    resolved_db = db_path or settings.resolved_database_path
    try:
        init_db(resolved_db)
        logger.info(f"Database connection verified at: {resolved_db}")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    # 2. Initialize Google Sheets (optional fallback)
    sheets_client: GoogleSheetsClient | None = None
    if enable_sheets:
        sheets_client = GoogleSheetsClient()
        if settings.has_google_credentials:
            sheets_client.connect()
        else:
            if not mock:
                logger.warning(
                    f"Google credentials not found at '{settings.resolved_google_credentials_path}'. "
                    "Google Sheets syncing will be skipped."
                )

    # 3. Instantiate Collector
    collector: BaseCollector
    if mock:
        collector = MockFacebookCollector()
    else:
        active_token = token or settings.facebook_access_token
        if not active_token:
            error_msg = (
                "Facebook access token is missing.\n"
                "Please set FACEBOOK_ACCESS_TOKEN in .env or pass --token <TOKEN>,\n"
                "or run with --mock flag to test with simulated data."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        collector = FacebookCollector(
            access_token=active_token,
            api_base_url=settings.facebook_api_base_url,
        )

    # 4. Collect Posts
    try:
        posts = collector.collect_posts(
            source_id=effective_source_id, limit=actual_limit
        )
        logger.info(f"Collected {len(posts)} posts")
    except Exception as e:
        logger.error(f"Collector encountered fatal error: {e}")
        raise

    # 5. Process Posts through Pipeline
    stats = process_posts(posts, db_path=resolved_db, sheets_client=sheets_client)

    logger.info(f"Found {stats.matched_count} matching posts")
    logger.info(f"Added {stats.new_leads_count} new leads")
    if stats.duplicate_count > 0:
        logger.info(f"Skipped {stats.duplicate_count} duplicate posts")
    if stats.error_count > 0:
        logger.warning(f"Encountered {stats.error_count} processing errors")

    return stats


def print_cli_summary(stats: PipelineStats) -> None:
    """Print clean user-facing CLI summary block."""
    print()
    print("Starting Facebook Lead Collector...")
    print()
    print(f"Collected: {stats.collected_count} posts")
    print(f"Keyword matched: {stats.matched_count}")
    print(f"Duplicates: {stats.duplicate_count}")
    print(f"New leads: {stats.new_leads_count}")
    print()
    if stats.new_leads:
        print("New leads:")
        for idx, lead in enumerate(stats.new_leads, 1):
            print(f"{idx}. {lead.author} | {lead.keyword} | {lead.post_url}")
        print()
    print("Finished.")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Facebook Lead Collector - Automated Tutoring Lead Extraction"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode with simulated data (no Facebook/Google credentials required)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Facebook Group URL, Page URL, or numeric ID to collect posts from",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Facebook Graph API Access Token (overrides .env)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of posts to fetch (default from config: 100)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Custom path to SQLite database file",
    )
    parser.add_argument(
        "--schedule",
        type=int,
        default=0,
        metavar="MINUTES",
        help="Run periodically every N minutes",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize the SQLite database schema and exit",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()

    if args.init_db:
        init_db(args.db_path)
        print("Database initialized successfully.")
        return

    # Periodic schedule mode
    if args.schedule > 0:
        logger.info(f"Running periodic scheduler every {args.schedule} minute(s)...")
        try:
            iteration = 1
            while True:
                logger.info(f"--- Starting run cycle #{iteration} ---")
                try:
                    stats = run(
                        source_id=args.source,
                        mock=args.mock,
                        limit=args.limit,
                        db_path=args.db_path,
                        token=args.token,
                    )
                    print_cli_summary(stats)
                except Exception as e:
                    logger.error(f"Cycle #{iteration} encountered error: {e}")

                iteration += 1
                logger.info(f"Sleeping for {args.schedule} minute(s)... (Press Ctrl+C to stop)")
                time.sleep(args.schedule * 60)
        except KeyboardInterrupt:
            logger.info("Periodic scheduler stopped by user.")
            sys.exit(0)
    else:
        # Single run execution
        try:
            stats = run(
                source_id=args.source,
                mock=args.mock,
                limit=args.limit,
                db_path=args.db_path,
                token=args.token,
            )
            print_cli_summary(stats)
        except ValueError as e:
            print(f"\n[!] Configuration Error: {e}\n", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
