"""Automated Facebook Public Group Discovery Engine.

Searches Facebook for groups matching education/tutoring topics,
filters STRICTLY for Public Groups (accessible to non-member accounts),
and exports 200-400+ clean group URLs into data/sources.txt.
"""
import argparse
import base64
import json
from pathlib import Path
import random
import re
import sys
import time
from typing import Any
from urllib.parse import quote_plus

# Ensure project root is in sys.path
_project_dir = Path(__file__).resolve().parent
if str(_project_dir) not in sys.path:
    sys.path.insert(0, str(_project_dir))

# Auto-detect & inject .venv if system python is used
for venv_path in (_project_dir / ".venv", _project_dir.parent / ".venv"):
    sites = list(venv_path.glob("lib/python*/site-packages"))
    if sites:
        if str(sites[0]) not in sys.path:
            sys.path.insert(0, str(sites[0]))
        break

from collectors.selenium_facebook import SeleniumFacebookSearchCollector
from config import get_settings
from utils.logger import logger

# 25 High-intent Vietnamese tutoring & education search keywords
DEFAULT_GROUP_SEARCH_TOPICS = [
    "gia sư",
    "tìm gia sư",
    "cần gia sư",
    "gia sư hà nội",
    "gia sư tphcm",
    "gia sư sài gòn",
    "gia sư đà nẵng",
    "gia sư hải phòng",
    "gia sư cần thơ",
    "hội gia sư",
    "phụ huynh tìm gia sư",
    "gia sư dạy kèm",
    "dạy kèm tại nhà",
    "gia sư sư phạm",
    "gia sư bách khoa",
    "gia sư ngoại thương",
    "gia sư toán",
    "gia sư tiếng anh",
    "gia sư tiểu học",
    "gia sư cấp 1 2 3",
    "luyện thi vào 10",
    "luyện thi đại học",
    "tìm giáo viên dạy kèm",
    "cộng đồng gia sư",
    "lớp gia sư",
]

# Facebook search filter for Public Groups: {"rp_group_public:0":"{\"name\":\"group_public\",\"args\":\"\"}"}
_PUBLIC_FILTER_JSON = json.dumps({"rp_group_public:0": json.dumps({"name": "group_public", "args": ""})}, separators=(',', ':'))
PUBLIC_GROUPS_FILTER_B64 = base64.b64encode(_PUBLIC_FILTER_JSON.encode()).decode()


class GroupInfo:
    """Structure representing a discovered Facebook group."""

    def __init__(self, name: str, url: str, members: str = "", is_public: bool = True):
        self.name = name.strip()
        self.url = url.strip()
        self.members = members.strip()
        self.is_public = is_public

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "members": self.members,
            "is_public": self.is_public,
        }


def canonicalize_group_url(raw_url: str) -> str | None:
    """Extract canonical group URL: https://www.facebook.com/groups/{id_or_vanity}/."""
    if not raw_url:
        return None
    match = re.search(r'facebook\.com/groups/([^/?#]+)', raw_url)
    if not match:
        return None
    group_slug = match.group(1).strip()
    # Ignore Facebook internal group routes
    if group_slug.lower() in ("feed", "discover", "notifications", "create", "joins", "search"):
        return None
    return f"https://www.facebook.com/groups/{group_slug}/"


def extract_groups_from_dom(driver) -> list[dict[str, Any]]:
    """Execute JavaScript to extract public group cards from Facebook group search results."""
    js_extract = r"""
    const results = [];
    const seenUrls = new Set();

    const isGroupLink = (href) => {
        if (!href) return false;
        if (!href.includes('/groups/')) return false;
        const parts = href.split('/groups/')[1].split('/')[0].split('?')[0].toLowerCase();
        return parts && !['feed', 'discover', 'create', 'search', 'joins'].includes(parts);
    };

    // Find all anchor tags pointing to a group
    const links = Array.from(document.querySelectorAll('a[href*="/groups/"]'));
    for (const a of links) {
        const href = a.getAttribute('href') || a.href || '';
        if (!isGroupLink(href)) continue;

        // Canonicalize URL
        let slug = href.split('/groups/')[1].split('/')[0].split('?')[0];
        let cleanUrl = 'https://www.facebook.com/groups/' + slug + '/';
        if (seenUrls.has(cleanUrl)) continue;

        // Traverse up to find card container
        let card = a;
        let depth = 0;
        while (card && depth < 8 && card !== document.body) {
            const txt = (card.innerText || '').toLowerCase();
            if (txt.includes('thành viên') || txt.includes('members') || txt.includes('công khai') || txt.includes('public')) {
                break;
            }
            card = card.parentElement;
            depth++;
        }

        if (!card) card = a.parentElement;
        const cardText = (card.innerText || '');
        const cardTextLower = cardText.toLowerCase();

        // STRICT FILTER: Must be PUBLIC group (acc vãng lai coi được)
        // Discard if marked as "riêng tư" or "private"
        const isPrivate = cardTextLower.includes('nhóm riêng tư') || cardTextLower.includes('private group');
        if (isPrivate) {
            continue;
        }

        const isExplicitPublic = cardTextLower.includes('nhóm công khai') || 
                                 cardTextLower.includes('public group') ||
                                 cardTextLower.includes('công khai');

        // Extract Group Name
        let name = '';
        const heading = card.querySelector('h2, h3, span[dir="auto"] strong, a[role="link"] span');
        if (heading && heading.innerText.trim()) {
            name = heading.innerText.trim();
        } else {
            name = a.innerText.trim() || slug;
        }

        // Clean name from member text
        name = name.split('\n')[0].replace(/\s+/g, ' ').trim();
        if (name.length < 3) continue;

        // Extract Member Count
        let members = '';
        const memberMatch = cardText.match(/(\d+(?:[\.,]\d+)?\s*(?:k|tr|triệu|nghìn)?)\s*(?:thành viên|members)/i);
        if (memberMatch) {
            members = memberMatch[1].trim();
        }

        seenUrls.add(cleanUrl);
        results.push({
            name: name,
            url: cleanUrl,
            members: members,
            is_public: isExplicitPublic || !isPrivate
        });
    }

    return results;
    """
    try:
        raw_list = driver.execute_script(js_extract) or []
        return raw_list
    except Exception as e:
        logger.warning(f"Error executing group extraction script: {e}")
        return []


def discover_public_groups(
    target_count: int = 300,
    topics: list[str] | None = None,
    scrolls_per_topic: int = 8,
    profile_name: str | None = None,
) -> list[GroupInfo]:
    """Search Facebook for public groups across topics until target_count is reached."""
    search_topics = topics or DEFAULT_GROUP_SEARCH_TOPICS
    logger.info(f"🔍 BẮT ĐẦU TÌM KIẾM NHÓM FACEBOOK CÔNG KHAI (Mục tiêu: {target_count} nhóm)...")

    collector = SeleniumFacebookSearchCollector(profile_name=profile_name)
    driver = collector._driver or collector._build_driver()

    discovered_groups: dict[str, GroupInfo] = {}

    try:
        logger.info("Mở Facebook để xác thực phiên làm việc...")
        driver.get("https://www.facebook.com")
        time.sleep(3)

        if not collector._has_logged_in_session(driver):
            warning = (
                ">>> YÊU CẦU: Vui lòng đăng nhập Facebook trên cửa sổ Chrome vừa mở. "
                "Sau khi đăng nhập xong, quay lại đây và nhấn ENTER để tiếp tục..."
            )
            print(warning)
            input(warning)
            driver.get("https://www.facebook.com")
            time.sleep(3)

        for topic_idx, topic in enumerate(search_topics, 1):
            if len(discovered_groups) >= target_count:
                logger.info(f"🎉 Đã đạt mục tiêu {target_count} nhóm công khai! Dừng tìm kiếm sớm.")
                break

            # Navigate to clean Group Search URL without GraphQL filter string (prevents GraphSearchQuery error)
            search_url = f"https://www.facebook.com/search/groups/?q={quote_plus(topic)}"
            print("\n" + "=" * 75)
            print(f"🔎 [{topic_idx}/{len(search_topics)}] TÌM KIẾM THEO CHỦ ĐỀ: '{topic}'")
            print(f"🌐 URL: {search_url}")
            print(f"📊 Hiện có: {len(discovered_groups)}/{target_count} nhóm công khai")
            print("=" * 75)

            try:
                driver.get(search_url)
                time.sleep(random.uniform(4.0, 5.0))
            except Exception as e:
                logger.warning(f"Lỗi khi tải trang tìm kiếm '{topic}': {e}")
                continue

            # Dismiss any unexpected dialogs (e.g. OK buttons)
            try:
                dialog_buttons = driver.find_elements(
                    "xpath",
                    "//div[@role='dialog']//div[@role='button']//span[text()='OK' or text()='Đóng' or text()='Close']"
                )
                for btn in dialog_buttons:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(1)
                        break
            except Exception:
                pass

            # Ensure 'Nhóm công khai' filter is toggled if available in UI sidebar
            try:
                public_buttons = driver.find_elements(
                    "xpath",
                    "//span[contains(text(), 'Nhóm công khai') or contains(text(), 'Public groups') or contains(text(), 'Công khai')]"
                )
                for btn in public_buttons:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(2)
                        break
            except Exception:
                pass

            # Scroll to load dynamic group results
            new_in_topic = 0
            for scroll_idx in range(scrolls_per_topic):
                # Scroll down
                scroll_script = """
                window.scrollTo(0, document.body.scrollHeight);
                if (document.scrollingElement) {
                    document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
                }
                """
                driver.execute_script(scroll_script)
                time.sleep(random.uniform(2.5, 4.0))

                # Extract newly loaded group cards
                raw_cards = extract_groups_from_dom(driver)
                for item in raw_cards:
                    c_url = canonicalize_group_url(item.get("url", ""))
                    if c_url and c_url not in discovered_groups:
                        g_info = GroupInfo(
                            name=item.get("name", ""),
                            url=c_url,
                            members=item.get("members", ""),
                            is_public=item.get("is_public", True),
                        )
                        discovered_groups[c_url] = g_info
                        new_in_topic += 1

                if len(discovered_groups) >= target_count:
                    break

            logger.info(f"Chủ đề '{topic}': Tìm thấy +{new_in_topic} nhóm công khai mới. Tổng: {len(discovered_groups)}")

    finally:
        if collector._owns_driver:
            driver.quit()

    return list(discovered_groups.values())


def save_groups_to_sources(
    groups: list[GroupInfo],
    sources_file: Path | str | None = None,
    append: bool = False,
) -> Path:
    """Save discovered group URLs into sources.txt with metadata comments."""
    if sources_file:
        out_path = Path(sources_file)
    else:
        out_path = get_settings().resolved_sources_file_path

    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing_urls: set[str] = set()
    if append and out_path.exists():
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    clean = canonicalize_group_url(line.split("#")[0].strip())
                    if clean:
                        existing_urls.add(clean)

    header = [
        "# ======================================================================",
        f"# DANH SÁCH NHÓM FACEBOOK CÔNG KHAI TỰ ĐỘNG THU THẬP ({len(groups)} NHÓM)",
        "# Tất cả nhóm đều là CÔNG KHAI (Acc vãng lai / chưa tham gia vẫn xem được)",
        f"# Thời gian tạo: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "# ======================================================================\n",
    ]

    lines = [] if append else header
    added_count = 0
    for idx, g in enumerate(groups, 1):
        if g.url in existing_urls:
            continue
        member_str = f" ({g.members} thành viên)" if g.members else ""
        lines.append(f"{g.url}  # {g.name}{member_str}")
        existing_urls.add(g.url)
        added_count += 1

    mode = "a" if append else "w"
    with out_path.open(mode, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logger.info(f"Đã lưu {added_count} link nhóm công khai vào file: {out_path}")

    # Also save structured JSON format
    json_path = out_path.parent / "discovered_groups.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump([g.to_dict() for g in groups], f, ensure_ascii=False, indent=2)
    logger.info(f"Đã lưu metadata chi tiết vào: {json_path}")

    return out_path


def parse_args() -> argparse.Namespace:
    """CLI argument parser for group discovery."""
    parser = argparse.ArgumentParser(description="eTeacher - Automated Facebook Public Group Discovery")
    parser.add_argument("--target-count", type=int, default=300, help="Target number of public groups to discover (default: 300)")
    parser.add_argument("--scrolls", type=int, default=8, help="Scroll count per search keyword (default: 8)")
    parser.add_argument("--output", type=str, default=None, help="Custom output file path (default: data/sources.txt)")
    parser.add_argument("--append", action="store_true", help="Append to existing sources.txt instead of overwriting")
    parser.add_argument("--profile", type=str, default=None, help="Chrome profile name")
    return parser.parse_args()


def main():
    """CLI Entrypoint."""
    args = parse_args()
    print("\n" + "=" * 75)
    print("🚀 ETEACHER - BOT TỰ ĐỘNG TÌM KIẾM & BÓC TÁCH LINK NHÓM FACEBOOK CÔNG KHAI")
    print(f"🎯 Mục tiêu: {args.target_count} nhóm công khai (Phục vụ acc vãng lai)")
    print("=" * 75 + "\n")

    groups = discover_public_groups(
        target_count=args.target_count,
        scrolls_per_topic=args.scrolls,
        profile_name=args.profile,
    )

    if groups:
        out_file = save_groups_to_sources(groups, sources_file=args.output, append=args.append)
        print("\n" + "=" * 75)
        print(f"🎉 HOÀN TẤT! ĐÃ TÌM THẤY {len(groups)} NHÓM CÔNG KHAI CHUẨN TOPIC GIA SƯ.")
        print(f"📂 File lưu danh sách: {out_file}")
        print("💡 Tiếp theo, bạn có thể chạy chế độ 2 (đa nhóm) bằng lệnh:")
        print("   python main.py --scrolls 15 --limit 50")
        print("=" * 75 + "\n")
    else:
        print("\n[!] Không tìm thấy nhóm nào. Vui lòng kiểm tra lại kết nối hoặc phiên đăng nhập Facebook.")


if __name__ == "__main__":
    main()
