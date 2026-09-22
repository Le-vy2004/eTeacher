"""Facebook public-post search collector using an existing Chrome profile."""
from datetime import datetime
import hashlib
from pathlib import Path
import random
import shutil
import sys
import time
from typing import Any
from urllib.parse import quote_plus

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import BaseCollector
from config import get_settings
from models.post import FacebookPost
from utils.logger import logger


class SeleniumFacebookSearchCollector(BaseCollector):
    """Collect visible Facebook search results with a locally logged-in Chrome profile."""

    def __init__(
        self,
        user_data_dir: str | Path | None = None,
        profile_name: str | None = None,
        scrolls: int = 3,
        sleep_range: tuple[float, float] = (4.0, 7.0),
        driver: Any | None = None,
    ):
        settings = get_settings()
        self.user_data_dir = Path(user_data_dir or settings.resolved_chrome_user_data_path).expanduser()
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
            from selenium.common.exceptions import TimeoutException
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
            raise ValueError("PROFILE_NAME must contain a Chrome profile directory name, usually 'Default'.")

        self.user_data_dir = self._prepare_user_data_dir()

        # Clean stale lock files to prevent startup crashes on Linux
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "LOCK"):
            for lock_file in (
                self.user_data_dir / lock_name,
                self.user_data_dir / self.profile_name / lock_name,
            ):
                try:
                    if lock_file.is_file() or lock_file.is_symlink():
                        lock_file.unlink(missing_ok=True)
                except OSError:
                    pass

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
        driver.set_page_load_timeout(30)
        return driver

    @staticmethod
    def _parse_time(raw_time: str) -> datetime:
        from utils.date_parser import parse_facebook_time
        return parse_facebook_time(raw_time)

    @staticmethod
    def _clean_post_url(raw_url: str) -> str:
        """Sanitize Facebook URL by stripping tracking parameters while keeping critical query IDs."""
        if not raw_url:
            return ""
        try:
            import re
            import urllib.parse
            parsed = urllib.parse.urlparse(raw_url)
            path = parsed.path.rstrip("/")
            if "/posts/" in path:
                base, post_id = path.rsplit("/posts/", 1)
                clean_id = post_id.split("/")[0].split(",")[0]
                return f"https://www.facebook.com{base}/posts/{clean_id}/"
            if "/permalink/" in path:
                base, perm_id = path.rsplit("/permalink/", 1)
                clean_id = perm_id.split("/")[0].split(",")[0]
                return f"https://www.facebook.com{base}/permalink/{clean_id}/"

            qs = urllib.parse.parse_qs(parsed.query)
            if "multi_permalinks" in qs and qs["multi_permalinks"]:
                pid = qs["multi_permalinks"][0].split(",")[0]
                group_match = re.search(r"/groups/([^/]+)", path)
                if group_match and pid:
                    return f"https://www.facebook.com/groups/{group_match.group(1)}/posts/{pid}/"

            important_keys = ["story_fbid", "id", "fbid", "set"]
            clean_qs = {k: qs[k][0].split(",")[0] for k in important_keys if k in qs and qs[k]}
            if clean_qs:
                return f"https://www.facebook.com{path}?{urllib.parse.urlencode(clean_qs)}"
            return f"https://www.facebook.com{path}"
        except Exception:
            return raw_url.split("?")[0].split(",")[0]

    @staticmethod
    def _has_logged_in_session(driver) -> bool:
        """Confirm the browser has an active Facebook session before searching."""
        current_url = (driver.current_url or "").lower()
        cookie_names = {cookie.get("name") for cookie in driver.get_cookies()}
        if "/login" in current_url or "/checkpoint" in current_url:
            logger.warning(
                f"Facebook session is on an authentication page: url={driver.current_url}, "
                f"title={driver.title!r}"
            )
            return False

        if "c_user" not in cookie_names:
            logger.warning(
                f"Facebook session cookie c_user is missing: url={driver.current_url}, "
                f"title={driver.title!r}, cookies={sorted(cookie_names)}"
            )
            return False

        from selenium.webdriver.common.by import By

        login_fields = driver.find_elements(
            By.CSS_SELECTOR,
            "input[name='email'], input[name='pass']",
        )
        return not login_fields

    def _extract_posts_js(self, driver, limit: int = 100) -> list[dict[str, Any]]:
        """Extract posts using client-side JavaScript executing in browser DOM."""
        js_script = r"""
        const maxLimit = arguments[0] || 100;

        // 1. Expand all 'Xem thêm' / 'See more' buttons
        try {
            const buttons = Array.from(document.querySelectorAll('div[role="button"], span[role="button"], span'));
            for (const btn of buttons) {
                const text = (btn.textContent || '').trim().toLowerCase();
                if (text === 'xem thêm' || text === 'see more' || text === 'xem thêm...') {
                    try { btn.click(); } catch(e) {}
                }
            }
        } catch(e) {}

        const isPostLink = (href) => {
            if (!href) return false;
            return (
                href.includes('/posts/') ||
                href.includes('/permalink/') ||
                href.includes('story_fbid=') ||
                href.includes('multi_permalinks=') ||
                (href.includes('/groups/') && href.includes('/user/'))
            );
        };

        const cleanUrl = (raw) => {
            if (!raw) return '';
            try {
                const u = new URL(raw, window.location.origin);
                const path = u.pathname.replace(/\/+$/, '');

                if (path.includes('/posts/') || path.includes('/permalink/')) {
                    let cleanPath = path;
                    if (cleanPath.includes('/posts/')) {
                        const parts = cleanPath.split('/posts/');
                        const pid = parts[1].split('/')[0].split(',')[0];
                        cleanPath = parts[0] + '/posts/' + pid;
                    } else if (cleanPath.includes('/permalink/')) {
                        const parts = cleanPath.split('/permalink/');
                        const pid = parts[1].split('/')[0].split(',')[0];
                        cleanPath = parts[0] + '/permalink/' + pid;
                    }
                    return u.origin + cleanPath + '/';
                }

                if (u.searchParams.has('multi_permalinks')) {
                    const rawPid = u.searchParams.get('multi_permalinks') || '';
                    const pid = rawPid.split(',')[0].trim();
                    const groupMatch = path.match(/\/groups\/([^\/]+)/);
                    const gid = groupMatch ? groupMatch[1] : '';
                    if (gid && pid) {
                        return `https://www.facebook.com/groups/${gid}/posts/${pid}/`;
                    }
                }

                if (u.searchParams.has('story_fbid')) {
                    const rawFbid = u.searchParams.get('story_fbid') || '';
                    const fbid = rawFbid.split(',')[0].trim();
                    const groupMatch = path.match(/\/groups\/([^\/]+)/);
                    if (groupMatch) {
                        return `https://www.facebook.com/groups/${groupMatch[1]}/posts/${fbid}/`;
                    }
                    const id = u.searchParams.get('id') || '';
                    return u.origin + path + '?story_fbid=' + fbid + (id ? '&id=' + id : '');
                }

                if (path.includes('/groups/') && path.includes('/user/')) {
                    const groupUserMatch = path.match(/\/groups\/([^\/]+)\/user\/([^\/]+)/);
                    if (groupUserMatch) {
                        return `https://www.facebook.com/groups/${groupUserMatch[1]}/user/${groupUserMatch[2]}/`;
                    }
                }

                return '';
            } catch(e) {
                return '';
            }
        };

        const isCommentEl = (el) => {
            if (!el) return false;
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (aria.includes('bình luận') || aria.includes('comment') || 
                aria.includes('phản hồi') || aria.includes('reply') ||
                aria.includes('viết bình luận') || aria.includes('cảm xúc') ||
                aria.includes('thích') || aria.includes('chia sẻ')) {
                return true;
            }
            if (el.closest('div[role="article"][aria-label*="bình luận" i]') ||
                el.closest('div[role="article"][aria-label*="comment" i]') ||
                el.closest('div[role="article"][aria-label*="phản hồi" i]') ||
                el.closest('div[role="article"][aria-label*="reply" i]')) {
                return true;
            }
            if (el.closest('form') || el.closest('ul')) return true;
            return false;
        };

        // 2. Locate post container elements (strictly excluding comment articles)
        const candidateCards = [];
        const seenElements = new Set();

        // Strategy A: Elements with role="article" that are NOT comments
        document.querySelectorAll('div[role="article"]').forEach(el => {
            if (!seenElements.has(el) && !isCommentEl(el)) {
                seenElements.add(el);
                candidateCards.push(el);
            }
        });

        // Strategy B: Direct children of feed
        document.querySelectorAll('div[role="feed"] > div').forEach(el => {
            if (!seenElements.has(el) && !isCommentEl(el) && (el.innerText || '').trim().length > 30) {
                seenElements.add(el);
                candidateCards.push(el);
            }
        });

        // Strategy C: Ancestors of post links
        document.querySelectorAll('a[href]').forEach(a => {
            if (isCommentEl(a)) return;
            const href = a.getAttribute('href') || '';
            if (isPostLink(href)) {
                let parent = a.parentElement;
                let depth = 0;
                let chosen = null;
                while (parent && depth < 12 && parent !== document.body) {
                    if (isCommentEl(parent)) {
                        chosen = null;
                        break;
                    }
                    if (parent.getAttribute('role') === 'article' && !isCommentEl(parent)) {
                        chosen = parent;
                        break;
                    }
                    if (parent.parentElement && parent.parentElement.getAttribute('role') === 'feed') {
                        chosen = parent;
                        break;
                    }
                    const len = (parent.innerText || '').length;
                    if (len > 40 && len < 8000 && !chosen && !isCommentEl(parent)) {
                        chosen = parent;
                    }
                    parent = parent.parentElement;
                    depth++;
                }
                if (chosen && !seenElements.has(chosen) && !isCommentEl(chosen)) {
                    seenElements.add(chosen);
                    candidateCards.push(chosen);
                }
            }
        });

        // Strategy D: Fallback to main text blocks
        if (candidateCards.length === 0) {
            document.querySelectorAll('div[role="main"] div[dir="auto"]').forEach(el => {
                if (isCommentEl(el)) return;
                let p = el.parentElement;
                let depth = 0;
                while (p && depth < 8 && p !== document.body) {
                    if (isCommentEl(p)) break;
                    const txt = (p.innerText || '').trim();
                    if (txt.length > 50 && txt.length < 6000 && !seenElements.has(p)) {
                        seenElements.add(p);
                        candidateCards.push(p);
                        break;
                    }
                    p = p.parentElement;
                    depth++;
                }
            });
        }

        // 3. Extract properties from each candidate card
        const results = [];
        const seenUrls = new Set();

        for (const card of candidateCards) {
            if (results.length >= maxLimit) break;

            const allLinks = Array.from(card.querySelectorAll('a[href]')).filter(a => !isCommentEl(a));
            let postUrl = '';
            for (const a of allLinks) {
                const href = a.getAttribute('href') || a.href || '';
                if (isPostLink(href)) {
                    const cleaned = cleanUrl(href);
                    if (cleaned) {
                        postUrl = cleaned;
                        if (cleaned.includes('/posts/') || cleaned.includes('/permalink/')) {
                            break;
                        }
                    }
                }
            }

            if (!postUrl || /^https?:\/\/[^\/]+\/groups\/[^\/]+\/?(#.*)?$/i.test(postUrl)) {
                continue;
            }

            if (seenUrls.has(postUrl)) {
                continue;
            }

            // Extract message content ONLY from main post body (stripping comments entirely)
            let content = '';

            // Priority 1: Dedicated post message preview containers
            const previewEls = Array.from(card.querySelectorAll('div[data-ad-preview="message"], div[data-ad-comet-preview="message"]'));
            for (const p of previewEls) {
                if (isCommentEl(p)) continue;
                const txt = (p.innerText || '').trim();
                if (txt.length > 20) {
                    content = txt;
                    break;
                }
            }

            // Priority 2: Clone card and sanitize by pruning comments, reply trees, action bars and input forms
            if (!content || content.length < 15) {
                const clone = card.cloneNode(true);

                // Remove comments
                clone.querySelectorAll('div[role="article"]').forEach(a => {
                    if (isCommentEl(a)) a.remove();
                });

                // Remove any element with comment / reaction aria-label
                clone.querySelectorAll('[aria-label]').forEach(el => {
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    if (aria.includes('bình luận') || aria.includes('comment') || 
                        aria.includes('phản hồi') || aria.includes('reply') ||
                        aria.includes('viết bình luận') || aria.includes('cảm xúc') ||
                        aria.includes('thích') || aria.includes('chia sẻ')) {
                        el.remove();
                    }
                });

                // Remove comment input form, textareas, uls
                clone.querySelectorAll('form, ul, input, textarea').forEach(e => e.remove());

                // Remove interaction action buttons
                clone.querySelectorAll('div[role="button"], span[role="button"]').forEach(b => {
                    const bText = (b.innerText || '').trim().toLowerCase();
                    if (['thích', 'like', 'bình luận', 'comment', 'chia sẻ', 'share', 'gửi'].includes(bText)) {
                        b.remove();
                    }
                });

                const segments = [];
                clone.querySelectorAll('div[dir="auto"], span[dir="auto"]').forEach(el => {
                    if (isCommentEl(el)) return;
                    const t = (el.innerText || '').trim();
                    if (t.length > 15 && !segments.some(s => s.includes(t) || t.includes(s))) {
                        segments.push(t);
                    }
                });

                if (segments.length > 0) {
                    content = segments.join('\\n\\n');
                } else {
                    const rawText = (clone.innerText || '').trim();
                    const lines = rawText.split('\\n').map(l => l.trim()).filter(Boolean);
                    const filtered = lines.filter(l => {
                        const lower = l.toLowerCase();
                        return !(
                            lower === 'thích' || lower === 'like' ||
                            lower === 'bình luận' || lower === 'comment' ||
                            lower === 'chia sẻ' || lower === 'share' ||
                            lower.startsWith('viết bình luận') ||
                            lower.startsWith('xem thêm bình luận') ||
                            lower.includes('phù hợp nhất') ||
                            lower.includes('tất cả bình luận')
                        );
                    });
                    content = filtered.join('\\n');
                }
            }

            if (!content || content.length < 15) {
                continue;
            }

            // Reject Group Header Banner elements that describe group members/rules
            const lowerContent = content.toLowerCase();
            if ((lowerContent.includes('nhóm công khai') || lowerContent.includes('nhóm riêng tư')) && lowerContent.includes('thành viên')) {
                continue;
            }

            seenUrls.add(postUrl);

            // Extract author cleanly from header
            let author = 'Facebook User';
            const headings = Array.from(card.querySelectorAll('h2 a, h3 a, h4 a, strong a, a[role="link"] strong, span[dir="auto"] strong, a[role="link"]'));
            for (const h of headings) {
                if (isCommentEl(h)) continue;
                const href = h.getAttribute('href') || (h.closest('a') ? h.closest('a').getAttribute('href') : '');
                if (href && (href.includes('/groups/') && !href.includes('/user/')) && !href.includes('/profile.php')) {
                    continue;
                }
                const txt = (h.innerText || '').trim();
                if (txt && txt.length >= 2 && txt.length < 50) {
                    const lower = txt.toLowerCase();
                    if (!lower.includes('bình luận') && 
                        !lower.includes('thành viên') && 
                        !lower.includes('tạo bài viết') &&
                        !lower.includes('xem thêm') &&
                        !lower.includes('chia sẻ') &&
                        !lower.includes('thích') &&
                        !lower.includes('chỉ báo trạng thái') &&
                        !lower.includes('đang hoạt động') &&
                        !lower.includes('phù hợp nhất')) {
                        author = txt.split('\n')[0].trim();
                        break;
                    }
                }
            }

            // Extract time
            let rawTime = '';
            const timeEl = card.querySelector('time[datetime], abbr[data-utime]');
            if (timeEl) {
                rawTime = timeEl.getAttribute('datetime') || timeEl.getAttribute('data-utime') || (timeEl.innerText || '').trim();
            }
            if (!rawTime) {
                const timeCandidates = card.querySelectorAll('a[href*="/posts/"] span, a[href*="/permalink/"] span, a[role="link"] span, span[dir="auto"]');
                for (const span of timeCandidates) {
                    const aria = (span.getAttribute('aria-label') || '').trim();
                    const txt = (span.innerText || '').trim();
                    if (aria && (aria.includes('lúc') || aria.includes('ngày') || aria.includes('giờ') || aria.includes('tháng') || aria.includes('hôm qua') || aria.includes('vừa xong') || aria.includes('ago'))) {
                        rawTime = aria;
                        break;
                    }
                    if (txt && /^(vừa xong|\d+\s*(phút|giờ|tiếng|ngày|tuần|tháng|năm|min|hr|d|w|m|y)|hôm qua)/i.test(txt)) {
                        rawTime = txt;
                        break;
                    }
                }
            }

            results.push({
                post_url: postUrl,
                author: author,
                content: content,
                raw_time: rawTime
            });
        }

        return results;
        """
        try:
            return driver.execute_script(js_script, limit) or []
        except Exception as e:
            logger.warning(f"Client JavaScript post extraction encountered error: {e}")
            return []

    def _search_via_ui(self, driver, keyword: str) -> None:
        """Search via Facebook's top search input and switch to Posts tab."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        logger.info(f"Using Facebook search bar to search for: '{keyword}'...")

        search_selectors = [
            "input[aria-label*='Tìm kiếm trên Facebook']",
            "input[placeholder*='Tìm kiếm trên Facebook']",
            "input[aria-label*='Search Facebook']",
            "input[placeholder*='Search Facebook']",
            "input[aria-label*='Tìm kiếm']",
            "input[placeholder*='Tìm kiếm']",
            "input[aria-label*='Search']",
            "input[placeholder*='Search']",
            "input[type='search']",
            "input[role='combobox']",
            "form input",
        ]

        search_input = None
        for sel in search_selectors:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    search_input = el
                    break
            if search_input:
                break

        if not search_input:
            icon_selectors = [
                "div[aria-label*='Tìm kiếm']",
                "div[aria-label*='Search']",
                "a[aria-label*='Tìm kiếm']",
                "a[aria-label*='Search']",
                "svg[aria-label*='Tìm kiếm']",
            ]
            for sel in icon_selectors:
                for icon in driver.find_elements(By.CSS_SELECTOR, sel):
                    if icon.is_displayed():
                        try:
                            icon.click()
                            time.sleep(1.5)
                            break
                        except Exception:
                            pass
                for sel_in in search_selectors:
                    for el in driver.find_elements(By.CSS_SELECTOR, sel_in):
                        if el.is_displayed():
                            search_input = el
                            break
                    if search_input:
                        break
                if search_input:
                    break

        if search_input:
            logger.info(f"Located search bar. Typing '{keyword}'...")
            try:
                search_input.click()
                time.sleep(0.5)
                search_input.send_keys(Keys.CONTROL + "a")
                search_input.send_keys(Keys.BACKSPACE)
                for ch in keyword:
                    search_input.send_keys(ch)
                    time.sleep(0.03)
                time.sleep(1)
                search_input.send_keys(Keys.RETURN)
                logger.info("Pressed Enter. Waiting for search results to load...")
                time.sleep(5)
            except Exception as e:
                logger.warning(f"Error typing into search input: {e}")
                from urllib.parse import quote_plus
                driver.get(f"https://www.facebook.com/search/posts/?q={quote_plus(keyword)}")
                time.sleep(4)
        else:
            logger.warning("Search bar input not found via UI, navigating directly...")
            from urllib.parse import quote_plus
            driver.get(f"https://www.facebook.com/search/posts/?q={quote_plus(keyword)}")
            time.sleep(4)

        # Switch to 'Bài viết' (Posts) tab
        try:
            logger.info("Switching to 'Bài viết' (Posts) tab in search filters...")
            tabs = driver.find_elements(
                By.CSS_SELECTOR,
                "a[href*='/search/posts/'], a[href*='/search/posts']"
            )
            clicked = False
            for tab in tabs:
                if tab.is_displayed():
                    tab.click()
                    clicked = True
                    logger.info("Clicked 'Bài viết' (Posts) tab successfully.")
                    time.sleep(3)
                    break
            if not clicked:
                spans = driver.find_elements(
                    By.XPATH,
                    "//span[text()='Bài viết' or text()='Posts' or text()='Bài viết công khai']"
                )
                for s in spans:
                    if s.is_displayed():
                        s.click()
                        logger.info("Clicked 'Bài viết' span filter.")
                        time.sleep(3)
                        break
        except Exception as e:
            logger.debug(f"Filter tab click non-fatal: {e}")

    def collect_posts(self, source_id: str, limit: int = 100, max_age_days: int = 30) -> list[FacebookPost]:
        """Search and extract Facebook posts matching source_id and keywords."""
        from selenium.common.exceptions import TimeoutException

        target = (source_id or "").strip()
        if not target:
            raise ValueError("A non-empty search keyword or source URL is required.")

        group_url = None
        keyword = None
        if "||" in target:
            group_url, keyword = target.split("||", 1)
        elif target.startswith("http://") or target.startswith("https://") or "facebook.com" in target:
            group_url = target
        else:
            keyword = target

        search_keyword = keyword or "tìm gia sư"

        logger.info("Initializing Chrome WebDriver with isolated profile...")
        driver = self._driver or self._build_driver()
        try:
            logger.info("Opening Facebook homepage to verify session...")
            driver.get("https://www.facebook.com")
        except TimeoutException:
            logger.warning("Facebook warm-up page timed out; continuing with current session.")
            driver.execute_script("window.stop();")
        time.sleep(4)

        posts: list[FacebookPost] = []
        try:
            if not self._has_logged_in_session(driver):
                warning = (
                    "Facebook is not logged in. Please log in manually in the opened Chrome window."
                )
                logger.warning(warning)
                print(warning)
                input(
                    ">>> ACTION REQUIRED: Please log in to Facebook on the opened Chrome window. "
                    "After you successfully log in and see the newsfeed, come back here and press ENTER to continue..."
                )
                try:
                    driver.get("https://www.facebook.com")
                except TimeoutException:
                    logger.warning("Facebook refresh timed out; continuing with current session.")
                    driver.execute_script("window.stop();")

            if group_url:
                clean_group_base = group_url.rstrip("/")
                logger.info(f"Navigating directly to Group feed: {clean_group_base}")
                try:
                    driver.get(clean_group_base)
                    time.sleep(5)
                except TimeoutException:
                    driver.execute_script("window.stop();")
                logger.info(f"Loaded Group page successfully: {driver.title!r}. Extracting feed posts...")
            else:
                # Search directly via top search bar on Facebook homepage when no URL is provided (Global Search)
                self._search_via_ui(driver, search_keyword)

            time.sleep(random.uniform(*self.sleep_range))

            # Smart multi-container scrolling with incremental extraction and early stop
            scroll_count = max(self.scrolls, 3)
            logger.info(f"Scrolling up to {scroll_count} times to load dynamic feed content...")
            raw_posts_dict: dict[str, dict[str, Any]] = {}
            stagnant_scrolls = 0
            prev_height = 0

            for scroll_idx in range(scroll_count):
                scroll_script = """
                window.scrollTo(0, document.body.scrollHeight);
                if (document.scrollingElement) {
                    document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
                }
                document.querySelectorAll('div[role="feed"], div[role="main"]').forEach(el => {
                    el.scrollTop = el.scrollHeight;
                });
                return document.body.scrollHeight;
                """
                try:
                    new_height = driver.execute_script(scroll_script) or 0
                except Exception:
                    new_height = 0
                time.sleep(random.uniform(*self.sleep_range))

                # Incrementally capture posts to prevent virtual DOM recycle loss
                current_batch = self._extract_posts_js(driver, limit=limit)
                new_batch_count = 0
                for item in current_batch:
                    p_url = item.get("post_url")
                    if p_url and p_url not in raw_posts_dict:
                        raw_posts_dict[p_url] = item
                        new_batch_count += 1

                logger.info(
                    f"Scroll {scroll_idx + 1}/{scroll_count} completed. "
                    f"Discovered {new_batch_count} new candidate(s) (total: {len(raw_posts_dict)})."
                )

                if len(raw_posts_dict) >= limit:
                    logger.info(f"Reached requested limit of {limit} posts early.")
                    break

                if new_height == prev_height and new_batch_count == 0:
                    stagnant_scrolls += 1
                    if stagnant_scrolls >= 2:
                        logger.info("No new content loaded after consecutive scrolls; stopping early.")
                        break
                else:
                    stagnant_scrolls = 0
                prev_height = new_height

            raw_posts = list(raw_posts_dict.values())
            logger.info(f"JavaScript post extractor retrieved {len(raw_posts)} candidate post(s).")

            seen_urls: set[str] = set()
            for item in raw_posts:
                if len(posts) >= limit:
                    break
                content = (item.get("content") or "").strip()
                post_url = self._clean_post_url(item.get("post_url") or "")
                author = item.get("author") or "Facebook User"
                raw_time = item.get("raw_time") or ""

                import re
                if not post_url or re.match(r"^https?://[^/]+/groups/[^/]+/?(#.*)?$", post_url):
                    continue
                if not content or post_url in seen_urls:
                    continue
                seen_urls.add(post_url)

                parsed_time = self._parse_time(raw_time)
                if max_age_days:
                    from utils.date_parser import is_within_days
                    if not is_within_days(parsed_time, days=max_age_days):
                        logger.debug(f"Bỏ qua bài viết cũ hơn {max_age_days} ngày: {parsed_time} ({post_url})")
                        continue

                post_id = hashlib.sha1(post_url.encode("utf-8")).hexdigest()
                posts.append(
                    FacebookPost(
                        post_id=post_id,
                        group_name="Facebook Search" if not group_url else group_url,
                        content=content,
                        author=author,
                        post_time=parsed_time,
                        post_url=post_url,
                    )
                )

        finally:
            if self._owns_driver:
                driver.quit()

        logger.info(f"Collected {len(posts)} post(s) from Facebook.")
        return posts