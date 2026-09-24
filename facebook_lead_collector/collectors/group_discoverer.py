"""Automated Facebook Group Discovery and Sources Updater."""
from datetime import datetime
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote

# Ensure project root is in sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from collectors.selenium_facebook import SeleniumFacebookSearchCollector
from config import get_settings
from database.sqlite_db import load_sources_from_file, save_source_to_db
from utils.logger import logger
from utils.text_utils import normalize_text


def _clean_group_url(raw_url: str) -> str:
    """Normalize Facebook group URL to canonical https://www.facebook.com/groups/<id>/ format."""
    if not raw_url:
        return ""
    # Strip protocol, domain, query params, hash
    clean = raw_url.split("?")[0].split("#")[0].strip()
    match = re.search(r"facebook\.com/groups/([^/?#]+)", clean)
    if match:
        group_id = match.group(1).rstrip("/")
        # Ignore non-group subpaths
        if group_id.lower() in [
            "feed", "joins", "discover", "categories", "create",
            "notifications", "search", "chats", "events"
        ]:
            return ""
        return f"https://www.facebook.com/groups/{group_id}/"
    return ""


def discover_facebook_groups(
    keyword: str = "tìm gia sư",
    limit: int = 15,
    scrolls: int = 6,
    sources_file: str | Path | None = None,
) -> list[dict[str, str]]:
    """Search Facebook for groups matching a keyword and save newly discovered groups to sources.txt.

    Args:
        keyword: Search query (e.g. 'tìm gia sư').
        limit: Target maximum number of new groups to add.
        scrolls: Number of page scrolls to load dynamic search results.
        sources_file: Path to sources.txt file (defaults to settings.resolved_sources_file_path).

    Returns:
        List of newly discovered group dictionaries with 'name' and 'url'.
    """
    settings = get_settings()
    target_sources_path = (
        Path(sources_file) if sources_file else settings.resolved_sources_file_path
    )
    existing_urls = set(load_sources_from_file(target_sources_path))
    logger.info(f"Loaded {len(existing_urls)} existing groups from {target_sources_path.name}")

    collector = SeleniumFacebookSearchCollector()
    logger.info("Initializing Chrome browser with project profile...")
    driver = collector._build_driver()

    discovered_groups: list[dict[str, str]] = []

    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        logger.info(f"🔍 Đang tìm kiếm nhóm Facebook với từ khóa: '{keyword}'...")

        # Option A: Directly navigate to Facebook Group Search URL
        encoded_kw = quote(keyword.strip())
        search_url = f"https://www.facebook.com/search/groups/?q={encoded_kw}"
        logger.info(f"Điều hướng tới trang tìm kiếm nhóm: {search_url}")
        driver.get(search_url)
        time.sleep(5)

        # If redirected to login, wait briefly or notify
        if not collector._has_logged_in_session(driver):
            logger.warning("Phiên đăng nhập chưa hoạt động. Hãy kiểm tra profile Chrome.")

        # Scroll to load dynamic group results
        logger.info(f"Cuộn trang {scrolls} lần để tải thêm danh sách nhóm...")
        for i in range(1, scrolls + 1):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2.5)
            logger.info(f"Đã cuộn {i}/{scrolls} lần...")

        # JavaScript extraction of group cards
        js_extract_groups = r"""
        const results = [];
        const seenUrls = new Set();

        // Query all links pointing to Facebook groups
        const links = Array.from(document.querySelectorAll('a[href*="/groups/"]'));
        for (const a of links) {
            const href = a.href || a.getAttribute('href') || '';
            const match = href.match(/facebook\.com\/groups\/([^\/?#]+)/);
            if (!match) continue;

            const groupId = match[1].trim();
            const ignored = ['feed', 'joins', 'discover', 'categories', 'create', 'notifications', 'search', 'chats', 'events'];
            if (ignored.includes(groupId.toLowerCase())) continue;

            const cleanUrl = 'https://www.facebook.com/groups/' + groupId + '/';
            if (seenUrls.has(cleanUrl)) continue;

            // Extract group title: check inner text, heading, or parent element
            let name = '';
            const heading = a.querySelector('span[dir="auto"], strong, h2, h3, h4');
            if (heading && heading.innerText && heading.innerText.trim().length > 3) {
                name = heading.innerText.trim();
            } else if (a.innerText && a.innerText.trim().length > 3) {
                name = a.innerText.trim();
            }

            // If name not directly inside <a>, check parent card
            if (!name || name.length < 3) {
                let parent = a.parentElement;
                for (let d = 0; d < 4 && parent; d++) {
                    const span = parent.querySelector('span[dir="auto"], strong');
                    if (span && span.innerText && span.innerText.trim().length > 3) {
                        name = span.innerText.trim();
                        break;
                    }
                    parent = parent.parentElement;
                }
            }

            // Clean up name (remove notification counts or member count lines)
            if (name) {
                name = name.split('\n')[0].trim();
            } else {
                name = 'Nhóm Facebook - ' + groupId;
            }

            seenUrls.add(cleanUrl);
            results.push({ url: cleanUrl, name: name });
        }
        return results;
        """

        raw_results = driver.execute_script(js_extract_groups) or []
        logger.info(f"Tìm thấy tổng cộng {len(raw_results)} nhóm trên trang kết quả tìm kiếm.")

        seen_in_batch: set[str] = set()
        for item in raw_results:
            clean_url = _clean_group_url(item.get("url", ""))
            raw_name = normalize_text(item.get("name", ""))
            if not clean_url or clean_url in seen_in_batch:
                continue

            seen_in_batch.add(clean_url)

            # Check if group already exists in sources.txt
            if clean_url in existing_urls:
                continue

            discovered_groups.append({
                "url": clean_url,
                "name": raw_name or "Nhóm Gia Sư Facebook",
            })

            if len(discovered_groups) >= limit:
                break

    finally:
        driver.quit()

    # Append newly discovered groups into sources.txt
    if discovered_groups:
        target_sources_path.parent.mkdir(parents=True, exist_ok=True)
        current_content = target_sources_path.read_text(encoding="utf-8") if target_sources_path.exists() else ""
        
        # Count existing numbered items in file to continue sequential numbering
        existing_numbers = re.findall(r"#\s*(\d+)\.", current_content)
        start_idx = max([int(n) for n in existing_numbers], default=len(existing_urls)) + 1

        new_entries = []
        for idx, grp in enumerate(discovered_groups, start=start_idx):
            new_entries.append(f"# {idx}. {grp['name']}\n{grp['url']}\n")
            # Save to SQLite database as well
            save_source_to_db(grp["url"], name=grp["name"])

        append_text = "\n" + "\n".join(new_entries)
        with target_sources_path.open("a", encoding="utf-8") as f:
            f.write(append_text)

        logger.info(f"🎉 Đã lưu thành công {len(discovered_groups)} nhóm mới vào '{target_sources_path.name}'!")
    else:
        logger.info("Không có nhóm mới nào cần thêm (tất cả nhóm tìm thấy đã có trong danh sách).")

    return discovered_groups


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    import argparse
    parser = argparse.ArgumentParser(description="Tự động tìm kiếm nhóm Facebook và lưu vào sources.txt")
    parser.add_argument("--keyword", type=str, default="tìm gia sư", help="Từ khóa tìm kiếm nhóm (mặc định: 'tìm gia sư')")
    parser.add_argument("--limit", type=int, default=10, help="Số lượng nhóm mới tối đa cần lấy (mặc định: 10)")
    parser.add_argument("--scrolls", type=int, default=6, help="Số lần cuộn trang tìm kiếm (mặc định: 6)")
    args = parser.parse_args()

    print("=" * 70)
    print(f"🚀 BẮT ĐẦU TỰ ĐỘNG TÌM KIẾM NHÓM FACEBOOK: '{args.keyword}'")
    print("=" * 70)

    groups = discover_facebook_groups(
        keyword=args.keyword,
        limit=args.limit,
        scrolls=args.scrolls,
    )

    print("\n" + "=" * 70)
    print(f"✅ HOÀN TẤT! Đã tìm và thêm {len(groups)} nhóm mới vào data/sources.txt:")
    print("=" * 70)
    for i, g in enumerate(groups, 1):
        print(f"{i}. {g['name']}\n   -> {g['url']}")
    print()
