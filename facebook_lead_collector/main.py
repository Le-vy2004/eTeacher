"""Main entrypoint and pipeline execution for Facebook Lead Collector."""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

project_dir = Path(__file__).resolve().parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

# Auto-detect & inject project virtualenv (.venv) if global python is used
try:
    import dotenv
except ImportError:
    venv_sites = list(project_dir.glob(".venv/lib/python*/site-packages"))
    if venv_sites:
        sys.path.insert(0, str(venv_sites[0]))

from collectors.base import BaseCollector
from collectors.selenium_facebook import SeleniumFacebookSearchCollector
from config import get_settings
from database.sqlite_db import get_all_leads, get_sources_from_db, init_db, insert_lead, lead_exists, load_sources_from_file
from filters.keyword_filter import DEFAULT_KEYWORDS, find_matching_keywords
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
    keywords: list[str] | None = None,
) -> PipelineStats:
    """Process a list of Facebook posts through the lead qualification pipeline."""
    stats = PipelineStats(collected_count=len(posts))

    for post in posts:
        try:
            content = post.content
            if not content or not content.strip():
                continue

            matched_keywords = find_matching_keywords(content, keywords=keywords)
            if not matched_keywords:
                continue

            stats.matched_count += 1

            if lead_exists(post.post_url, db_path=db_path):
                stats.duplicate_count += 1
                continue

            lead = Lead(
                group_name=post.group_name,
                keyword=", ".join(matched_keywords),
                author=post.author,
                post_time=post.post_time,
                post_url=post.post_url,
                content=content,
                collected_at=datetime.now(),
            )

            if not insert_lead(lead, db_path=db_path):
                stats.duplicate_count += 1
                continue

            stats.new_leads_count += 1
            stats.new_leads.append(lead)

            if sheets_client and sheets_client.is_connected:
                sheets_client.append_lead(lead)

        except Exception as e:
            stats.error_count += 1
            logger.error(f"Error processing post {getattr(post, 'post_id', 'unknown')}: {e}")

    return stats


def run(
    source_id: str | None = None,
    limit: int | None = None,
    db_path: Path | str | None = None,
    enable_sheets: bool = True,
    keyword: str | None = None,
    profile: str | None = None,
) -> PipelineStats:
    """Execute lead collection for a single source or keyword."""
    settings = get_settings()
    actual_limit = limit or settings.collector_limit
    effective_source = source_id or keyword or "https://www.facebook.com/groups/711749030995107/"

    resolved_db = db_path or settings.resolved_database_path
    init_db(resolved_db)

    sheets_client: GoogleSheetsClient | None = None
    if enable_sheets:
        sheets_client = GoogleSheetsClient()
        if settings.has_google_credentials:
            sheets_client.connect()

    collector: BaseCollector = SeleniumFacebookSearchCollector(profile_name=profile)
    posts = collector.collect_posts(source_id=effective_source, limit=actual_limit)
    logger.info(f"Collected {len(posts)} posts from source '{effective_source}'")

    custom_keywords = list(DEFAULT_KEYWORDS)
    if keyword and keyword not in custom_keywords:
        custom_keywords.insert(0, keyword)

    return process_posts(posts, db_path=resolved_db, sheets_client=sheets_client, keywords=custom_keywords)


def run_batch_sources(args: argparse.Namespace, target_sources: list[str]) -> PipelineStats:
    """Run raw data collection sequentially for target group/page URLs."""
    logger.info(f"🚀 BẮT ĐẦU CHẠY TUẦN TỰ QUÉT DATA VỚI {len(target_sources)} NHÓM / TRANG FACEBOOK:")
    combined_stats = PipelineStats()

    for idx, src in enumerate(target_sources, 1):
        print("\n" + "=" * 70)
        print(f"🚀 [{idx}/{len(target_sources)}] CHUYỂN TỚI NHÓM / TRANG: {src}")
        print("=" * 70)

        try:
            stats = run(
                source_id=src,
                limit=args.limit,
                db_path=args.db_path,
                keyword=args.keyword,
                profile=args.profile,
            )
            combined_stats.collected_count += stats.collected_count
            combined_stats.matched_count += stats.matched_count
            combined_stats.duplicate_count += stats.duplicate_count
            combined_stats.new_leads_count += stats.new_leads_count
            combined_stats.new_leads.extend(stats.new_leads)
        except Exception as e:
            logger.error(f"❌ Lỗi khi quét nguồn {src}: {e}")

    return combined_stats


def print_cli_summary(stats: PipelineStats) -> None:
    """Print user-facing CLI execution summary."""
    print("\nStarting Facebook Lead Collector...\n")
    print(f"Collected: {stats.collected_count} posts")
    print(f"Keyword matched: {stats.matched_count}")
    print(f"Duplicates: {stats.duplicate_count}")
    print(f"New leads: {stats.new_leads_count}\n")
    if stats.new_leads:
        print("New leads:")
        for idx, lead in enumerate(stats.new_leads, 1):
            print(f"{idx}. {lead.author} | {lead.keyword} | {lead.post_url}")
        print()
    print("Finished.")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Facebook Lead Collector - Automated Tutoring Lead Extraction")
    parser.add_argument("--source", type=str, default=None, help="Facebook Group/Page URL to collect posts from")
    parser.add_argument("--sources-file", type=str, default=None, help="Path to text file containing target URLs")
    parser.add_argument("--keyword", type=str, default=None, help="Keyword search fallback (e.g. 'tìm gia sư')")
    parser.add_argument("--profile", type=str, default=None, help="Chrome profile name (default: Profile 7)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of posts to fetch")
    parser.add_argument("--db-path", type=str, default=None, help="Custom path to SQLite database file")
    parser.add_argument("--schedule", type=int, default=0, metavar="MINUTES", help="Run periodically every N minutes")
    parser.add_argument("--init-db", action="store_true", help="Initialize SQLite database schema and exit")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()

    if args.init_db:
        init_db(args.db_path)
        print("Database initialized successfully.")
        return

    file_sources = load_sources_from_file(args.sources_file)
    db_sources = get_sources_from_db(args.db_path)
    all_sources = list(dict.fromkeys(file_sources + db_sources))

    def execute():
        if not args.source and all_sources:
            return run_batch_sources(args, all_sources)
        return run(
            source_id=args.source,
            limit=args.limit,
            db_path=args.db_path,
            keyword=args.keyword,
            profile=args.profile,
        )

    if args.schedule > 0:
        logger.info(f"Running periodic scheduler every {args.schedule} minute(s)...")
        try:
            iteration = 1
            while True:
                logger.info(f"--- Cycle #{iteration} ---")
                try:
                    stats = execute()
                    print_cli_summary(stats)
                except Exception as e:
                    logger.error(f"Cycle #{iteration} error: {e}")
                iteration += 1
                time.sleep(args.schedule * 60)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped.")
            sys.exit(0)
    else:
        try:
            stats = execute()
            print_cli_summary(stats)
        except Exception as e:
            print(f"\n[!] Execution Error: {e}\n", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
