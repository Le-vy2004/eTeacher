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
from database.sqlite_db import (
    filter_new_post_urls,
    get_all_leads,
    get_sources_from_db,
    init_db,
    insert_lead,
    insert_leads_batch,
    lead_exists,
    load_sources_from_file,
)
from filters.cleaner import clean_and_extract_lead_info
from filters.keyword_filter import DEFAULT_KEYWORDS, find_matching_keywords
from models.post import FacebookPost, Lead
from pydantic import BaseModel, Field
from sheets.google_sheets import GoogleSheetsClient
from utils.date_parser import is_within_days
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
    max_age_days: int = 30,
) -> PipelineStats:
    """Process a list of Facebook posts through the lead qualification and cleaning pipeline with batch optimization."""
    stats = PipelineStats(collected_count=len(posts))

    # Phase 1: Filter posts matching demand keywords and freshness cutoff
    matched_candidates: list[tuple[FacebookPost, list[str]]] = []
    candidate_urls: list[str] = []

    for post in posts:
        content = post.content
        if not content or not content.strip():
            continue
        if max_age_days and not is_within_days(post.post_time, days=max_age_days):
            continue
        matched_keywords = find_matching_keywords(content, author=post.author, keywords=keywords)
        if not matched_keywords:
            continue
        stats.matched_count += 1
        matched_candidates.append((post, matched_keywords))
        candidate_urls.append(post.post_url)

    if not matched_candidates:
        return stats

    # Phase 2: Batch deduplication query against SQLite
    new_urls = filter_new_post_urls(candidate_urls, db_path=db_path)
    stats.duplicate_count = len(matched_candidates) - len(new_urls)

    # Phase 3: Extract entity and clean leads for newly discovered posts
    leads_to_save: list[Lead] = []
    for post, matched_keywords in matched_candidates:
        if post.post_url not in new_urls:
            continue
        try:
            extracted_info = clean_and_extract_lead_info(post.content, author=post.author)
            # Loại bỏ bài gia sư đi tìm học sinh (Supply lead)
            if extracted_info.lead_type == "Gia sư nhận lớp":
                logger.info(f"Loại bỏ bài gia sư tìm học viên của '{post.author}' ({post.post_url})")
                continue

            lead = Lead(
                group_name=post.group_name,
                keyword=", ".join(matched_keywords),
                author=post.author,
                post_time=post.post_time,
                post_url=post.post_url,
                content=post.content,
                phone=extracted_info.phone,
                zalo_url=extracted_info.zalo_url,
                min_budget=extracted_info.min_budget,
                max_budget=extracted_info.max_budget,
                budget_unit=extracted_info.budget_unit,
                subject=extracted_info.subject,
                grade=extracted_info.grade,
                lead_type=extracted_info.lead_type,
                collected_at=datetime.now(),
            )
            leads_to_save.append(lead)
        except Exception as e:
            stats.error_count += 1
            logger.error(f"Error extracting lead info for post {getattr(post, 'post_id', 'unknown')}: {e}")

    # Phase 4: Batch database insertion in a single transaction
    if leads_to_save:
        inserted_count = insert_leads_batch(leads_to_save, db_path=db_path)
        stats.new_leads_count = inserted_count
        stats.new_leads = leads_to_save

        # Phase 5: Batch sync to Google Sheets (prevent rate limit 429)
        if sheets_client and sheets_client.is_connected:
            try:
                sheets_client.append_leads(leads_to_save)
            except Exception as e:
                logger.error(f"Error syncing batch leads to Google Sheets: {e}")

    return stats


def run(
    source_id: str | None = None,
    limit: int | None = None,
    scrolls: int | None = None,
    days: int = 30,
    db_path: Path | str | None = None,
    enable_sheets: bool = True,
    keyword: str | None = None,
    profile: str | None = None,
    driver: Any | None = None,
    sheets_client: GoogleSheetsClient | None = None,
) -> PipelineStats:
    """Execute lead collection for a single source or keyword."""
    settings = get_settings()
    actual_limit = limit or settings.collector_limit
    effective_source = source_id or keyword or "https://www.facebook.com/groups/711749030995107/"

    resolved_db = db_path or settings.resolved_database_path
    init_db(resolved_db)

    active_sheets_client = sheets_client
    if active_sheets_client is None and enable_sheets:
        active_sheets_client = GoogleSheetsClient()
        if settings.has_google_credentials:
            active_sheets_client.connect()

    collector: BaseCollector = SeleniumFacebookSearchCollector(
        profile_name=profile,
        scrolls=scrolls or 12,
        driver=driver,
    )
    posts = collector.collect_posts(source_id=effective_source, limit=actual_limit, max_age_days=days)
    logger.info(f"Collected {len(posts)} posts from source '{effective_source}'")

    custom_keywords = list(DEFAULT_KEYWORDS)
    if keyword and keyword not in custom_keywords:
        custom_keywords.insert(0, keyword)

    return process_posts(
        posts,
        db_path=resolved_db,
        sheets_client=active_sheets_client,
        keywords=custom_keywords,
        max_age_days=days,
    )


def run_batch_sources(args: argparse.Namespace, target_sources: list[str]) -> PipelineStats:
    """Run raw data collection sequentially for target group/page URLs or global search queries with persistent driver session."""
    logger.info(f"🚀 BẮT ĐẦU CHẠY TUẦN TỰ QUÉT DATA VỚI {len(target_sources)} NGUỒN / TỪ KHÓA (LỌC TRONG {args.days} NGÀY):")
    combined_stats = PipelineStats()

    settings = get_settings()
    resolved_db = args.db_path or settings.resolved_database_path
    init_db(resolved_db)

    # Pre-initialize shared Google Sheets client once
    shared_sheets: GoogleSheetsClient | None = None
    if settings.has_google_credentials:
        shared_sheets = GoogleSheetsClient()
        shared_sheets.connect()

    # Pre-initialize shared Chrome driver to prevent opening/closing browser 200 times
    collector_factory = SeleniumFacebookSearchCollector(
        profile_name=args.profile,
        scrolls=args.scrolls or 12,
    )
    shared_driver = collector_factory._build_driver()

    try:
        for idx, src in enumerate(target_sources, 1):
            print("\n" + "=" * 70)
            print(f"🚀 [{idx}/{len(target_sources)}] CHUYỂN TỚI NGUỒN / TỪ KHÓA: {src}")
            print("=" * 70)

            try:
                stats = run(
                    source_id=src,
                    limit=args.limit,
                    scrolls=args.scrolls,
                    days=args.days,
                    db_path=resolved_db,
                    keyword=args.keyword,
                    profile=args.profile,
                    driver=shared_driver,
                    sheets_client=shared_sheets,
                )
                combined_stats.collected_count += stats.collected_count
                combined_stats.matched_count += stats.matched_count
                combined_stats.duplicate_count += stats.duplicate_count
                combined_stats.new_leads_count += stats.new_leads_count
                combined_stats.new_leads.extend(stats.new_leads)
            except Exception as e:
                logger.error(f"❌ Lỗi khi quét nguồn {src}: {e}")
                err_msg = str(e).lower()
                if "invalid session id" in err_msg or "disconnected" in err_msg or "not connected to devtools" in err_msg:
                    logger.warning("WebDriver session disconnected. Re-initializing Chrome session...")
                    try:
                        shared_driver.quit()
                    except Exception:
                        pass
                    try:
                        shared_driver = collector_factory._build_driver()
                        logger.info("Chrome session re-initialized successfully.")
                    except Exception as reinit_err:
                        logger.error(f"Failed to restart Chrome driver: {reinit_err}")
    finally:
        try:
            shared_driver.quit()
        except Exception:
            pass

    return combined_stats


GLOBAL_SEARCH_QUERIES = [
    "cần gia sư",
    "tìm gia sư",
    "cần tìm gia sư",
    "tìm gia sư dạy kèm",
    "cần gia sư toán",
    "cần gia sư tiếng anh",
    "cần gia sư tiểu học",
    "tìm gia sư ôn thi vào 10",
]


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
    parser.add_argument("--source", type=str, default=None, help="Facebook Group/Page URL or keyword to collect from")
    parser.add_argument("--sources-file", type=str, default=None, help="Path to text file containing target URLs")
    parser.add_argument("--keyword", type=str, default=None, help="Keyword search fallback (e.g. 'tìm gia sư')")
    parser.add_argument("--global-search", action="store_true", help="Search globally across all of Facebook by keywords (not limited to groups)")
    parser.add_argument("--profile", type=str, default=None, help="Chrome profile name (default: Profile 7)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of posts to fetch per source")
    parser.add_argument("--scrolls", type=int, default=12, help="Number of scroll iterations to fetch deep history (default: 12, use 25-30 for 6 months)")
    parser.add_argument("--days", type=int, default=30, help="Maximum post age in days (default: 30 for 1 month)")
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

    file_sources = load_sources_from_file(args.sources_file) if args.sources_file else []
    all_sources = file_sources if file_sources else get_sources_from_db(args.db_path)

    def execute():
        if args.global_search:
            logger.info("🌍 Kích hoạt chế độ TÌM KIẾM TOÀN CẦU (GLOBAL FACEBOOK SEARCH)...")
            queries = [args.keyword] if args.keyword else GLOBAL_SEARCH_QUERIES
            return run_batch_sources(args, queries)
        if not args.source and all_sources:
            return run_batch_sources(args, all_sources)
        return run(
            source_id=args.source,
            limit=args.limit,
            scrolls=args.scrolls,
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
