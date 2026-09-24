"""Main entrypoint and pipeline execution for Facebook Lead Collector."""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

project_dir = Path(__file__).resolve().parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

# Auto-detect & inject project virtualenv (.venv) if global python is used
try:
    import dotenv
except ImportError:
    venv_sites = list(project_dir.glob(".venv/lib/python*/site-packages")) + list(project_dir.glob(".venv/Lib/site-packages"))
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
    max_age_days: int | None = 30,
    max_age_hours: float | None = None,
) -> PipelineStats:
    """Process a list of Facebook posts through the lead qualification and cleaning pipeline with batch optimization."""
    stats = PipelineStats(collected_count=len(posts))

    # Phase 1: Filter posts matching demand keywords and freshness cutoff
    matched_candidates: list[tuple[FacebookPost, list[str]]] = []
    candidate_urls: list[str] = []

    from utils.date_parser import is_within_time_window

    for post in posts:
        content = post.content
        if not content or not content.strip():
            continue
        if (max_age_hours or max_age_days) and not is_within_time_window(post.post_time, hours=max_age_hours, days=max_age_days):
            continue
        matched_keywords = find_matching_keywords(content, author=post.author, keywords=keywords)
        if not matched_keywords:
            continue
        stats.matched_count += 1
        matched_candidates.append((post, matched_keywords))
        candidate_urls.append(post.post_url)

    time_desc = f"{max_age_hours} giờ" if max_age_hours else f"{max_age_days or 30} ngày"
    if not matched_candidates:
        print(f"ℹ️ [Google Sheets] Nhóm này không có bài viết nào khớp từ khóa cần tìm gia sư (trong {time_desc} gần nhất). Không có lead để đẩy.")
        return stats

    # Phase 2: Batch deduplication query against SQLite
    new_db_urls = set(filter_new_post_urls(candidate_urls, db_path=db_path))
    stats.duplicate_count = len(matched_candidates) - len(new_db_urls)

    # Phase 3: Extract entity and clean leads for all qualified posts
    all_qualified_leads: list[Lead] = []
    leads_to_save_db: list[Lead] = []

    for post, matched_keywords in matched_candidates:
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
            all_qualified_leads.append(lead)
            if post.post_url in new_db_urls:
                leads_to_save_db.append(lead)
        except Exception as e:
            stats.error_count += 1
            logger.error(f"Error extracting lead info for post {getattr(post, 'post_id', 'unknown')}: {e}")

    # Phase 4: Batch database insertion in a single transaction
    if leads_to_save_db:
        inserted_count = insert_leads_batch(leads_to_save_db, db_path=db_path)
        stats.new_leads_count = inserted_count
        stats.new_leads = leads_to_save_db
        print(f"📥 [SQLite] Đã lưu {inserted_count} lead mới vào cơ sở dữ liệu local.")
    else:
        if all_qualified_leads:
            print(f"ℹ️ [SQLite] Tất cả {len(all_qualified_leads)} lead phù hợp đã tồn tại trong SQLite.")

    # Phase 5: Đẩy ngay lập tức data mới của group này lên Google Sheet trước khi chuyển group
    if sheets_client and sheets_client.is_connected:
        leads_to_push = [lead for lead in all_qualified_leads if not sheets_client.post_exists(lead.post_url)]
        if leads_to_push:
            print(f"\n📤 [Google Sheets] Đang đồng bộ {len(leads_to_push)} lead mới của nhóm lên Google Sheet...")
            try:
                appended = sheets_client.append_leads(leads_to_push)
                print(f"✅ [Google Sheets] Đã đẩy thành công {appended} lead lên Google Sheet ('{sheets_client.sheet_name}' -> '{sheets_client.worksheet_name}')!")
            except Exception as e:
                logger.error(f"Error syncing batch leads to Google Sheets: {e}")
                print(f"❌ [Google Sheets] Lỗi khi đẩy lên Google Sheet: {e}")
        else:
            if all_qualified_leads:
                print(f"ℹ️ [Google Sheets] Toàn bộ {len(all_qualified_leads)} lead phù hợp của nhóm này đã có sẵn trên Google Sheet (không cần đẩy trùng).")
            else:
                print(f"ℹ️ [Google Sheets] Không có lead mới hợp lệ cần đẩy lên Google Sheet.")
    else:
        print("ℹ️ [Google Sheets] Google Sheets chưa được kết nối hoặc đã tắt đồng bộ.")

    return stats


def run(
    source_id: str | None = None,
    limit: int | None = None,
    scrolls: int | None = None,
    days: int | None = None,
    hours: float | None = 3.0,
    db_path: Path | str | None = None,
    enable_sheets: bool = True,
    keyword: str | None = None,
    profile: str | None = None,
    driver: Any | None = None,
    sheets_client: GoogleSheetsClient | None = None,
) -> PipelineStats:
    """Execute lead collection for a single source or keyword."""
    settings = get_settings()
    actual_limit = limit if (limit is not None and limit > 0) else None
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
        scrolls=scrolls or 40,
        driver=driver,
    )
    posts = collector.collect_posts(
        source_id=effective_source,
        limit=actual_limit,
        max_age_days=days if not hours else None,
        max_age_hours=hours,
    )
    logger.info(f"Collected {len(posts)} posts from source '{effective_source}'")

    custom_keywords = list(DEFAULT_KEYWORDS)
    if keyword and keyword not in custom_keywords:
        custom_keywords.insert(0, keyword)

    return process_posts(
        posts,
        db_path=resolved_db,
        sheets_client=active_sheets_client,
        keywords=custom_keywords,
        max_age_days=days if not hours else None,
        max_age_hours=hours,
    )


def run_batch_sources(args: argparse.Namespace, target_sources: list[str]) -> PipelineStats:
    """Run raw data collection sequentially for target group/page URLs or global search queries with persistent driver session."""
    time_desc = f"{args.hours} giờ" if args.hours else f"{args.days or 30} ngày"
    logger.info(f"🚀 BẮT ĐẦU CHẠY TUẦN TỰ QUÉT DATA VỚI {len(target_sources)} NGUỒN / TỪ KHÓA (LỌC TRONG {time_desc}):")
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
        scrolls=args.scrolls or 40,
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
                    hours=args.hours,
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

                if stats.new_leads_count > 0:
                    print(f"🎉 Hoàn tất nhóm [{idx}/{len(target_sources)}]: Đã lưu SQLite & Đẩy xong {stats.new_leads_count} lead mới lên Google Sheet.")
                else:
                    print(f"🏁 Hoàn tất nhóm [{idx}/{len(target_sources)}]: Đã kiểm tra xong, không có lead mới cần thêm.")
                if idx < len(target_sources):
                    print("⏩ Chuẩn bị chuyển sang nhóm tiếp theo...\n")
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
    parser.add_argument("--sources-file", "--source-file", dest="sources_file", type=str, default=None, help="Path to text file containing target URLs")
    parser.add_argument("--keyword", type=str, default=None, help="Keyword search fallback (e.g. 'tìm gia sư')")
    parser.add_argument("--global-search", action="store_true", help="Search globally across all of Facebook by keywords (not limited to groups)")
    parser.add_argument("--profile", type=str, default=None, help="Chrome profile name (default: Profile 7)")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of posts to fetch per source (0 or omitted for unlimited within --hours/--days)")
    parser.add_argument("--scrolls", type=int, default=0, help="Number of scroll iterations (0 or omitted for dynamic timeline auto-stop)")
    parser.add_argument("--days", "--day", dest="days", type=int, default=None, help="Maximum post age in days (e.g. --days 30 for 1 month)")
    parser.add_argument("--hours", "--hour", dest="hours", type=float, default=None, help="Maximum post age in hours (default: 3.0 for last 3 hours)")
    parser.add_argument("--db-path", type=str, default=None, help="Custom path to SQLite database file")
    parser.add_argument("--schedule", type=int, default=0, metavar="MINUTES", help="Run periodically every N minutes")
    parser.add_argument("--init-db", action="store_true", help="Initialize SQLite database schema and exit")
    parser.add_argument("--sync-sheets", action="store_true", help="Sync all leads from local SQLite database to Google Sheets")
    parser.add_argument("--add-friends", action="store_true", help="Automatically send Facebook friend requests to authors from Google Sheets / DB")
    parser.add_argument("--friend-limit", type=int, default=15, help="Maximum number of friend requests to send per run (default: 15)")
    parser.add_argument("--min-delay", type=float, default=15.0, help="Minimum delay (seconds) between friend requests (default: 15)")
    parser.add_argument("--max-delay", type=float, default=30.0, help="Maximum delay (seconds) between friend requests (default: 30)")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()

    # Mặc định quét trong vòng 3 giờ gần nhất nếu không chỉ định rõ --hours hoặc --days
    if args.hours is None and args.days is None:
        args.hours = 3.0

    if args.init_db:
        init_db(args.db_path)
        print("Database initialized successfully.")
        return

    if args.sync_sheets:
        leads = get_all_leads(args.db_path)
        print(f"Đã đọc {len(leads)} lead từ cơ sở dữ liệu local (leads.db).")
        client = GoogleSheetsClient()
        if not client.connect():
            print("[X] Không thể kết nối Google Sheets. Kiểm tra lại file service_account.json.", file=sys.stderr)
            sys.exit(1)
        appended = client.append_leads(leads)
        print(f"[✓] Đã đồng bộ thành công {appended} lead mới từ local lên Google Sheets ('{client.sheet_name}' -> '{client.worksheet_name}')!")
        return

    if args.add_friends:
        from actions.friend_requester import FriendRequester
        requester = FriendRequester(
            profile_name=args.profile,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            max_requests=args.friend_limit,
        )
        requester.run_auto_friend_workflow(limit=args.friend_limit)
        return

    if args.sources_file:
        all_sources = load_sources_from_file(args.sources_file)
    else:
        file_sources = load_sources_from_file()
        db_sources = get_sources_from_db(args.db_path)
        all_sources = list(dict.fromkeys(file_sources + db_sources))

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
            days=args.days,
            hours=args.hours,
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
