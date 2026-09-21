"""Facebook Group search collector using an existing Chrome profile.

Navigates directly to specified Facebook Group(s), searches by keyword inside the group,
and extracts verified post permalinks, author, post time, and content.
"""
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import random
import re
import shutil
import sys
import time
from typing import Any
from urllib.parse import quote_plus, urlparse, parse_qs, urlencode

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import BaseCollector
from config import get_settings
from models.post import FacebookPost
from utils.logger import logger


def normalize_group_url(raw: str) -> str:
    """Normalize user input to a canonical Facebook group URL."""
    clean = (raw or "").strip().rstrip("/")
    if not clean:
        return ""
    if clean.startswith("http://") or clean.startswith("https://"):
        parsed = urlparse(clean)
        path = parsed.path.rstrip("/")
        return f"https://www.facebook.com{path}"
    if clean.isdigit():
        return f"https://www.facebook.com/groups/{clean}"
    if clean.startswith("groups/"):
        return f"https://www.facebook.com/{clean}"
    return f"https://www.facebook.com/groups/{clean}"


def build_group_search_url(group_url: str, keyword: str) -> str:
    """Construct Facebook group search URL."""
    clean_group = normalize_group_url(group_url)
    if clean_group.endswith("/search"):
        return f"{clean_group}/?q={quote_plus(keyword)}"
    return f"{clean_group}/search/?q={quote_plus(keyword)}"


class SeleniumFacebookSearchCollector(BaseCollector):
    """Collect visible Facebook posts from Facebook Groups with a locally logged-in Chrome profile."""

    def __init__(
        self,
        user_data_dir: str | Path | None = None,
        profile_name: str | None = None,
        scrolls: int = 4,
        sleep_range: tuple[float, float] = (3.5, 6.0),
        driver: Any | None = None,
    ):
        settings = get_settings()
        self.user_data_dir = Path(user_data_dir or settings.chrome_user_data).expanduser()
        raw_profile = profile_name or settings.chrome_profile_name
        if raw_profile and str(raw_profile).isdigit():
            self.profile_name = f"Profile {raw_profile}"
        else:
            self.profile_name = str(raw_profile)
        self.scrolls = scrolls
        self.sleep_range = sleep_range
        self._driver = driver
        self._owns_driver = driver is None

    def _prepare_user_data_dir(self) -> Path:
        """Use an isolated local data directory when Chrome's default is configured."""
        if self.user_data_dir.name.lower() != "user data":
            return self.user_data_dir

        isolated_dir = self.user_data_dir.parent / "Selenium User Data"
        isolated_profile = isolated_dir / self.profile_name
        source_profile = self.user_data_dir / self.profile_name
        logger.info(f"Synchronizing isolated Chrome profile for '{self.profile_name}'...")

        def safe_copy(src, dst):
            try:
                shutil.copy2(src, dst)
            except (PermissionError, OSError):
                pass

        try:
            shutil.copytree(
                source_profile,
                isolated_profile,
                dirs_exist_ok=True,
                copy_function=safe_copy,
                ignore=shutil.ignore_patterns(
                    "Singleton*",
                    "Cache*",
                    "Code Cache",
                    "Dawn*",
                    "GPUCache",
                    "Service Worker",
                    "IndexedDB",
                    "File System",
                    "Shared Dictionary",
                    "Extensions*",
                    "Extension *",
                    "Local Extension Settings",
                    "blob_storage",
                    "WebStorage",
                    "databases",
                    "optimization_guide*",
                    "Crashpad",
                    "BrowserMetrics*",
                    "GrShaderCache",
                    "ShaderCache",
                    "Sync Data*",
                    "Sessions*",
                    "Current Session",
                    "Current Tabs",
                    "Last Session",
                    "Last Tabs",
                    "LOCK",
                    "*-journal",
                ),
            )
            logger.info(f"Synchronized isolated Chrome profile at {isolated_profile}")
        except OSError as error:
            logger.warning(f"Profile synchronization noticed non-fatal issue: {error}")

        source_local_state = self.user_data_dir / "Local State"
        isolated_local_state = isolated_dir / "Local State"
        if source_local_state.is_file():
            try:
                safe_copy(source_local_state, isolated_local_state)
            except OSError:
                pass
        return isolated_dir

    def _build_driver(self) -> Any:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except ImportError as error:
            raise RuntimeError(
                "Selenium mode requires the dependency. Run: pip install -r requirements.txt"
            ) from error

        if not self.user_data_dir:
            raise ValueError("CHROME_USER_DATA must point to an existing Chrome user-data directory.")
        if not self.user_data_dir.is_dir():
            raise ValueError(f"Chrome user-data directory does not exist: {self.user_data_dir}")
        if not self.profile_name:
            raise ValueError("PROFILE_NAME must contain a Chrome profile directory name, usually 'Profile 7' or 'Default'.")

        self.user_data_dir = self._prepare_user_data_dir()
        options = Options()
        options.page_load_strategy = "eager"
        options.add_argument(f"--user-data-dir={self.user_data_dir}")
        options.add_argument(f"--profile-directory={self.profile_name}")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--remote-debugging-port=0")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(35)
        return driver

    @staticmethod
    def _parse_time(raw_time: str) -> datetime:
        """Parse human-readable Vietnamese Facebook timestamps or ISO format."""
        if not raw_time:
            return datetime.now()
        raw = raw_time.strip().lower()

        # Check ISO datetime
        try:
            return datetime.fromisoformat(raw.replace("z", "+00:00"))
        except (TypeError, ValueError):
            pass

        now = datetime.now()
        # "vừa xong" / "just now"
        if "vừa xong" in raw or "just now" in raw:
            return now

        # Minutes ago: "15 phút", "15 mins", "15m"
        m_match = re.search(r"(\d+)\s*(phút|min|m\b)", raw)
        if m_match:
            mins = int(m_match.group(1))
            return now - timedelta(minutes=mins)

        # Hours ago: "2 giờ", "2 hrs", "2h"
        h_match = re.search(r"(\d+)\s*(giờ|hr|h\b)", raw)
        if h_match:
            hrs = int(h_match.group(1))
            return now - timedelta(hours=hrs)

        # Days ago: "3 ngày", "3 days", "3d"
        d_match = re.search(r"(\d+)\s*(ngày|day|d\b)", raw)
        if d_match:
            days = int(d_match.group(1))
            return now - timedelta(days=days)

        # "Hôm qua lúc HH:MM"
        if "hôm qua" in raw or "yesterday" in raw:
            time_match = re.search(r"(\d{1,2}):(\d{2})", raw)
            yesterday = now - timedelta(days=1)
            if time_match:
                return yesterday.replace(hour=int(time_match.group(1)), minute=int(time_match.group(2)), second=0)
            return yesterday

        # "15 tháng 9 lúc 08:30" or "15 tháng 9, 2025"
        date_match = re.search(r"(\d{1,2})\s*tháng\s*(\d{1,2})", raw)
        if date_match:
            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year_match = re.search(r"(\d{4})", raw)
            year = int(year_match.group(1)) if year_match else now.year
            time_match = re.search(r"(\d{1,2}):(\d{2})", raw)
            hour = int(time_match.group(1)) if time_match else 0
            minute = int(time_match.group(2)) if time_match else 0
            try:
                return datetime(year, month, day, hour, minute)
            except ValueError:
                pass

        return now

    @staticmethod
    def _has_logged_in_session(driver) -> bool:
        """Confirm the browser has an active Facebook session."""
        current_url = (driver.current_url or "").lower()
        cookie_names = {cookie.get("name") for cookie in driver.get_cookies()}
        if "/login" in current_url or "/checkpoint" in current_url:
            return False
        if "c_user" not in cookie_names:
            return False

        from selenium.webdriver.common.by import By
        login_fields = driver.find_elements(
            By.CSS_SELECTOR,
            "input[name='email'], input[name='pass']",
        )
        return not login_fields

    def _extract_posts_js(self, driver, group_name_fallback: str, limit: int = 100) -> list[dict[str, Any]]:
        """Extract Facebook posts using robust JavaScript executing in browser DOM."""
        js_script = """
        const maxLimit = arguments[0] || 100;
        const defaultGroupName = arguments[1] || 'Facebook Group';

        // 1. Expand all 'Xem thêm' / 'See more' buttons to reveal full content
        try {
            const buttons = Array.from(document.querySelectorAll('div[role="button"], span[role="button"], span'));
            for (const btn of buttons) {
                const text = (btn.textContent || '').trim().toLowerCase();
                if (text === 'xem thêm' || text === 'see more' || text === 'xem thêm...') {
                    try { btn.click(); } catch(e) {}
                }
            }
        } catch(e) {}

        // Helper: Clean Facebook post permalink
        const cleanPostUrl = (raw) => {
            if (!raw) return '';
            try {
                const u = new URL(raw, window.location.origin);
                const path = u.pathname.replace(/\\/+$/, '');

                // Standard group post: /groups/123/posts/456 or /groups/slug/posts/456
                const postMatch = path.match(/(\\/groups\\/[^\\/]+\\/(?:posts|permalink)\\/\\d+)/);
                if (postMatch) {
                    return u.origin + postMatch[1] + '/';
                }

                // story_fbid pattern
                if (u.searchParams.has('story_fbid')) {
                    const fbid = u.searchParams.get('story_fbid');
                    const groupMatch = path.match(/(\\/groups\\/[^\\/]+)/);
                    if (groupMatch) {
                        return u.origin + groupMatch[1] + '/posts/' + fbid + '/';
                    }
                    const id = u.searchParams.get('id');
                    return u.origin + '/permalink.php?story_fbid=' + fbid + (id ? '&id=' + id : '');
                }

                // General post permalink
                if (path.includes('/posts/') || path.includes('/permalink/')) {
                    // Strip tracking params
                    ['__cft__[0]', '__tn__', 'ref', 'mibextid', 'fbclid', 'rdid'].forEach(p => u.searchParams.delete(p));
                    return u.origin + path + (u.search ? u.search : '') + (path.endsWith('/') ? '' : '/');
                }

                return '';
            } catch(e) {
                return '';
            }
        };

        // Helper: Find valid post permalink in a card
        const findPostUrl = (card) => {
            const links = Array.from(card.querySelectorAll('a[href]'));

            // Pass 1: Explicit post or permalink link
            for (const a of links) {
                const href = a.getAttribute('href') || a.href || '';
                if (!href || href.startsWith('#')) continue;
                // Exclude author/user links, hashtags, member links
                if (href.includes('/user/') || href.includes('/member') || href.includes('/hashtag/') || href.includes('/events/')) {
                    continue;
                }
                if (href.includes('/posts/') || href.includes('/permalink/') || href.includes('story_fbid=')) {
                    const cleaned = cleanPostUrl(href);
                    if (cleaned) return cleaned;
                }
            }

            // Pass 2: Timestamp anchor (has aria-label or relative time text)
            for (const a of links) {
                const href = a.getAttribute('href') || a.href || '';
                if (!href || href.startsWith('#')) continue;
                if (href.includes('/user/') || href.includes('/member') || href.includes('/hashtag/')) continue;

                const label = (a.getAttribute('aria-label') || '').toLowerCase();
                const text = (a.innerText || '').toLowerCase().trim();

                const isTime = (
                    label.includes('lúc') || label.includes('ngày') || label.includes('tháng') ||
                    label.includes('hôm qua') || label.includes('phút') || label.includes('giờ') ||
                    /\\d+\\s*(phút|giờ|ngày|tháng|min|hr|h|d)/.test(text) ||
                    text.includes('hôm qua') || text.includes('vừa xong')
                );

                if (isTime) {
                    const cleaned = cleanPostUrl(href);
                    if (cleaned) return cleaned;
                }
            }

            return '';
        };

        // Helper: Extract Author name
        const extractAuthor = (card) => {
            // Find links with profile or strong header
            const candidates = card.querySelectorAll('h2 a, h3 a, h4 a, strong a, a[role="link"] strong, span[dir="auto"] strong, a[href*="/user/"]');
            for (const el of candidates) {
                const anchor = el.tagName === 'A' ? el : el.closest('a');
                const text = (el.innerText || anchor?.innerText || '').trim();
                const href = anchor ? (anchor.getAttribute('href') || '') : '';

                if (!text || text.length > 50) continue;
                const lower = text.toLowerCase();
                if (lower.includes('nhóm') || lower.includes('tham gia') || lower.includes('xem')) continue;
                if (href.includes('/groups/') && !href.includes('/user/') && !href.includes('/posts/')) continue;

                return text;
            }
            return 'Facebook User';
        };

        // Helper: Extract timestamp
        const extractTime = (card) => {
            const timeEl = card.querySelector('time[datetime]');
            if (timeEl) {
                const dt = timeEl.getAttribute('datetime') || timeEl.innerText;
                if (dt) return dt.trim();
            }

            const links = card.querySelectorAll('a[role="link"], a[href]');
            for (const a of links) {
                const label = a.getAttribute('aria-label') || '';
                if (label && (label.includes('lúc') || label.includes('ngày') || label.includes('tháng') || label.includes('hôm qua') || label.includes('phút') || label.includes('giờ'))) {
                    return label.trim();
                }
            }

            for (const a of links) {
                const text = (a.innerText || '').trim();
                if (/\\d+\\s*(phút|giờ|ngày|tháng|min|hr|h|d)/.test(text) || text.includes('hôm qua') || text.includes('vừa xong')) {
                    return text;
                }
            }
            return '';
        };

        // Helper: Extract message content
        const extractContent = (card) => {
            let content = '';
            const msgEls = card.querySelectorAll('div[data-ad-preview="message"], div[dir="auto"]');
            if (msgEls.length > 0) {
                const segments = [];
                msgEls.forEach(m => {
                    const t = (m.innerText || '').trim();
                    if (t.length > 15 && !segments.some(s => s.includes(t) || t.includes(s))) {
                        segments.push(t);
                    }
                });
                if (segments.length > 0) {
                    content = segments.join('\\n\\n');
                }
            }

            if (!content || content.length < 20) {
                const rawText = (card.innerText || '').trim();
                const lines = rawText.split('\\n').map(l => l.trim()).filter(Boolean);
                const filtered = lines.filter(l => {
                    const lower = l.toLowerCase();
                    return !(
                        lower === 'thích' || lower === 'like' ||
                        lower === 'bình luận' || lower === 'comment' ||
                        lower === 'chia sẻ' || lower === 'share' ||
                        lower.startsWith('viết bình luận') ||
                        lower.startsWith('xem thêm bình luận') ||
                        lower.startsWith('tác giả') ||
                        lower.startsWith('quản trị viên')
                    );
                });
                content = filtered.join('\\n');
            }
            return content;
        };

        // 2. Identify candidate post cards
        const candidateCards = [];
        const seenElements = new Set();

        // Strategy 1: Feed direct children
        document.querySelectorAll('div[role="feed"] > div, div[role="main"] div[role="article"]').forEach(el => {
            if (!seenElements.has(el) && (el.innerText || '').trim().length > 30) {
                seenElements.add(el);
                candidateCards.push(el);
            }
        });

        // Strategy 2: Ancestors of post links
        if (candidateCards.length === 0) {
            document.querySelectorAll('a[href*="/posts/"], a[href*="/permalink/"]').forEach(a => {
                let p = a.parentElement;
                let depth = 0;
                let chosen = null;
                while (p && depth < 12 && p !== document.body) {
                    if (p.getAttribute('role') === 'article' || (p.parentElement && p.parentElement.getAttribute('role') === 'feed')) {
                        chosen = p;
                        break;
                    }
                    if ((p.innerText || '').length > 40 && !chosen) {
                        chosen = p;
                    }
                    p = p.parentElement;
                    depth++;
                }
                if (chosen && !seenElements.has(chosen)) {
                    seenElements.add(chosen);
                    candidateCards.push(chosen);
                }
            });
        }

        // 3. Extract posts
        const results = [];
        const seenUrls = new Set();

        for (const card of candidateCards) {
            if (results.length >= maxLimit) break;

            const postUrl = findPostUrl(card);
            // CRITICAL: Skip any post without a verified, accessible direct permalink!
            if (!postUrl || seenUrls.has(postUrl)) {
                continue;
            }

            const content = extractContent(card);
            if (!content || content.length < 15) {
                continue;
            }

            seenUrls.add(postUrl);
            const author = extractAuthor(card);
            const rawTime = extractTime(card);

            results.push({
                post_url: postUrl,
                author: author,
                content: content,
                raw_time: rawTime,
                group_name: defaultGroupName
            });
        }

        return results;
        """
        try:
            return driver.execute_script(js_script, limit, group_name_fallback) or []
        except Exception as e:
            logger.error(f"JavaScript DOM extraction failed: {e}", exc_info=True)
            return []

    def _get_page_group_name(self, driver, fallback_url: str) -> str:
        """Extract group name from DOM or title."""
        try:
            from selenium.webdriver.common.by import By
            # Check h1 tag in group header
            h1s = driver.find_elements(By.CSS_SELECTOR, "h1, div[role='main'] h1")
            for h in h1s:
                t = (h.text or "").strip()
                if t and len(t) < 80 and not t.lower().startswith("kết quả"):
                    return t
            title = (driver.title or "").split("|")[0].replace("Facebook", "").strip()
            if title and not title.lower().startswith("kết quả"):
                return title
        except Exception:
            pass
        return fallback_url

    def _discover_groups(self, driver, keyword: str, max_groups: int = 5) -> list[dict[str, str]]:
        """Search Facebook for Groups related to keyword and return discovered groups."""
        from selenium.common.exceptions import TimeoutException

        query = keyword.strip() or "tìm gia sư"
        groups_search_url = f"https://www.facebook.com/search/groups/?q={quote_plus(query)}"
        logger.info(f"Đang tự động tìm kiếm các Nhóm trên Facebook theo từ khóa '{query}'...")
        logger.info(f"URL tìm nhóm: {groups_search_url}")

        try:
            driver.get(groups_search_url)
            time.sleep(4.5)
        except TimeoutException:
            driver.execute_script("window.stop();")

        # Scroll down to load group results
        for s in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2.0)

        js_find_groups = """
        const groups = [];
        const seen = new Set();
        const invalid = new Set(['feed', 'discover', 'joins', 'create', 'categories', 'notifications', 'search', 'user', 'profile.php']);

        document.querySelectorAll('a[href*="/groups/"]').forEach(a => {
            try {
                const href = a.href || a.getAttribute('href') || '';
                const u = new URL(href, window.location.origin);
                const match = u.pathname.match(/^\\/groups\\/([^\\/]+)(?:\\/|$)/);
                if (match) {
                    const slug = match[1].toLowerCase();
                    if (!invalid.has(slug) && !slug.includes('search') && !slug.includes('user')) {
                        const cleanUrl = 'https://www.facebook.com/groups/' + match[1] + '/';
                        if (!seen.has(cleanUrl)) {
                            seen.add(cleanUrl);
                            let name = (a.innerText || '').trim();
                            if (!name || name.length < 3 || name.toLowerCase().includes('tham gia')) {
                                const card = a.closest('div[role="feed"] > div, div[role="main"] div') || a.parentElement?.parentElement;
                                const heading = card ? card.querySelector('h2, h3, strong, a[role="link"] span') : null;
                                if (heading && (heading.innerText || '').trim()) {
                                    name = heading.innerText.trim();
                                }
                            }
                            if (!name || name.toLowerCase().includes('tham gia')) {
                                name = 'Nhóm ' + match[1];
                            }
                            groups.push({ url: cleanUrl, name: name });
                        }
                    }
                }
            } catch(e) {}
        });
        return groups;
        """
        try:
            raw_groups = driver.execute_script(js_find_groups) or []
        except Exception as e:
            logger.error(f"Error executing group discovery script: {e}")
            raw_groups = []

        discovered = raw_groups[:max_groups]
        if discovered:
            logger.info(f"Tự động tìm thấy {len(discovered)} nhóm phù hợp trên Facebook:")
            for idx, g in enumerate(discovered, 1):
                logger.info(f"  {idx}. {g.get('name')} -> {g.get('url')}")
        else:
            logger.warning(f"Chưa tìm thấy nhóm nào với từ khóa '{query}'.")

        return discovered

    def collect_posts(self, source_id: str, limit: int = 100) -> list[FacebookPost]:
        """Navigate to Facebook Group(s), search by keyword, and extract posts."""
        from selenium.common.exceptions import TimeoutException

        target = (source_id or "").strip()

        # Parse group and keyword
        group_raw = None
        keyword = None
        if "||" in target:
            group_raw, keyword = target.split("||", 1)
        elif target.startswith("http://") or target.startswith("https://") or "facebook.com" in target or target.isdigit():
            group_raw = target
            keyword = "tìm gia sư"
        else:
            group_raw = None
            keyword = target or "tìm gia sư"

        settings = get_settings()
        final_group_raw = group_raw or settings.facebook_group_url or settings.facebook_source_id
        search_keyword = (keyword or "tìm gia sư").strip()

        logger.info(f"Initializing Chrome WebDriver (Profile: '{self.profile_name}')...")
        driver = self._driver or self._build_driver()
        posts: list[FacebookPost] = []
        seen_all_urls: set[str] = set()

        try:
            logger.info("Opening Facebook homepage to verify session...")
            try:
                driver.get("https://www.facebook.com")
            except TimeoutException:
                driver.execute_script("window.stop();")
            time.sleep(3.5)

            if not self._has_logged_in_session(driver):
                warning = "Facebook is not logged in. Please log in manually in the opened Chrome window."
                logger.warning(warning)
                print(warning)
                input(
                    ">>> ACTION REQUIRED: Please log in to Facebook on the opened Chrome window. "
                    "After you successfully log in, press ENTER to continue..."
                )
                try:
                    driver.get("https://www.facebook.com")
                except TimeoutException:
                    driver.execute_script("window.stop();")

            # Determine list of groups to scrape:
            # 1. If user gave group(s), use them.
            # 2. Otherwise, automatically search Facebook for relevant groups!
            group_items = []
            if final_group_raw:
                for g in final_group_raw.split(","):
                    if g.strip():
                        norm_url = normalize_group_url(g)
                        group_items.append({"url": norm_url, "name": norm_url})
            else:
                logger.info(
                    f"Không có link nhóm sẵn -> Tự động tìm kiếm các Nhóm liên quan trên Facebook theo từ khóa: '{search_keyword}'"
                )
                discovered = self._discover_groups(driver, search_keyword, max_groups=5)
                if not discovered and search_keyword != "gia sư":
                    logger.info("Thử mở rộng tìm kiếm nhóm với từ khóa 'gia sư'...")
                    discovered = self._discover_groups(driver, "gia sư", max_groups=5)
                group_items = discovered

            if not group_items:
                logger.error("Không xác định được nhóm Facebook nào để tìm bài. Vui lòng kiểm tra lại kết nối.")
                return []

            logger.info(f"Bắt đầu quét qua {len(group_items)} nhóm Facebook...")

            for g_info in group_items:
                if len(posts) >= limit:
                    break

                group_url = g_info["url"]
                group_name_hint = g_info.get("name") or group_url

                search_url = build_group_search_url(group_url, search_keyword)
                logger.info(f"\n---> Truy cập Nhóm: '{group_name_hint}'")
                logger.info(f"Dò tìm bài viết theo key '{search_keyword}': {search_url}")

                try:
                    driver.get(search_url)
                    time.sleep(4.5)
                except TimeoutException:
                    logger.warning(f"Timeout opening {search_url}; continuing with rendered DOM.")
                    driver.execute_script("window.stop();")

                group_display_name = self._get_page_group_name(driver, group_name_hint)

                # Dynamic scrolling to load feed results inside the group
                scroll_count = max(self.scrolls, 5)
                logger.info(f"Cuộn trang {scroll_count} lần để tải danh sách bài viết...")
                for scroll_idx in range(scroll_count):
                    scroll_script = """
                    window.scrollTo(0, document.body.scrollHeight);
                    if (document.scrollingElement) {
                        document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
                    }
                    document.querySelectorAll('div[role="feed"], div[role="main"]').forEach(el => {
                        el.scrollTop = el.scrollHeight;
                    });
                    """
                    driver.execute_script(scroll_script)
                    time.sleep(random.uniform(*self.sleep_range))

                logger.info("Trích xuất các bài viết và permalink thực tế...")
                raw_posts = self._extract_posts_js(driver, group_name_fallback=group_display_name, limit=limit)
                logger.info(f"Thu thập được {len(raw_posts)} bài viết có permalink hợp lệ từ nhóm này.")

                for item in raw_posts:
                    if len(posts) >= limit:
                        break
                    post_url = item.get("post_url") or ""
                    content = (item.get("content") or "").strip()
                    author = item.get("author") or "Facebook User"
                    raw_time = item.get("raw_time") or ""
                    grp_name = item.get("group_name") or group_display_name

                    if not post_url or not content or post_url in seen_all_urls:
                        continue
                    seen_all_urls.add(post_url)

                    post_id = hashlib.sha1(post_url.encode("utf-8")).hexdigest()
                    posts.append(
                        FacebookPost(
                            post_id=post_id,
                            group_name=grp_name,
                            content=content,
                            author=author,
                            post_time=self._parse_time(raw_time),
                            post_url=post_url,
                        )
                    )

        finally:
            if self._owns_driver:
                driver.quit()

        logger.info(f"\nHoàn tất: Thu thập được tổng cộng {len(posts)} bài viết có link hợp lệ từ các nhóm Facebook.")
        return posts