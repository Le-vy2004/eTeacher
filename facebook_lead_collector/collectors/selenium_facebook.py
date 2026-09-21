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
        try:
            return datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.now()

    @staticmethod
    def _post_url(article) -> str | None:
        from selenium.webdriver.common.by import By

        links = article.find_elements(By.CSS_SELECTOR, "a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            if "/posts/" in href or "story_fbid=" in href or "/permalink/" in href:
                return href.split("?")[0]
        return None

    @staticmethod
    def _clean_post_url(raw_url: str) -> str:
        """Sanitize Facebook URL by stripping tracking parameters while keeping critical query IDs."""
        if not raw_url:
            return ""
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(raw_url)
            path = parsed.path.rstrip("/")
            if "/posts/" in path or "/permalink/" in path:
                return f"https://www.facebook.com{path}"
            
            qs = urllib.parse.parse_qs(parsed.query)
            important_keys = ["story_fbid", "id", "fbid", "set"]
            clean_qs = {k: qs[k][0] for k in important_keys if k in qs and qs[k]}
            if clean_qs:
                return f"https://www.facebook.com{path}?{urllib.parse.urlencode(clean_qs)}"
            return f"https://www.facebook.com{path}"
        except Exception:
            return raw_url.split("?")[0]

    @staticmethod
    def _parse_time(raw_time: str) -> datetime:
        if not raw_time:
            return datetime.now()
        try:
            return datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.now()

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
                href.includes('/groups/') ||
                href.includes('/user/')
            );
        };

        const cleanUrl = (raw) => {
            if (!raw) return '';
            try {
                const u = new URL(raw, window.location.origin);
                const path = u.pathname.replace(/\/+$/, '');

                if (u.searchParams.has('multi_permalinks')) {
                    const pid = u.searchParams.get('multi_permalinks');
                    const groupMatch = path.match(/\/groups\/([^\/]+)/);
                    const gid = groupMatch ? groupMatch[1] : '';
                    if (gid && pid) {
                        return `https://www.facebook.com/groups/${gid}/posts/${pid}/`;
                    }
                }

                if (u.searchParams.has('story_fbid')) {
                    const fbid = u.searchParams.get('story_fbid');
                    const groupMatch = path.match(/\/groups\/([^\/]+)/);
                    if (groupMatch) {
                        return `https://www.facebook.com/groups/${groupMatch[1]}/posts/${fbid}/`;
                    }
                    const id = u.searchParams.get('id') || '';
                    return u.origin + path + '?story_fbid=' + fbid + (id ? '&id=' + id : '');
                }

                if (path.includes('/posts/') || path.includes('/permalink/')) {
                    return u.origin + path + '/';
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

        // 2. Locate post container elements
        const candidateCards = [];
        const seenElements = new Set();

        // Strategy A: Elements with role="article"
        document.querySelectorAll('div[role="article"]').forEach(el => {
            if (!seenElements.has(el)) {
                seenElements.add(el);
                candidateCards.push(el);
            }
        });

        // Strategy B: Direct children of feed
        document.querySelectorAll('div[role="feed"] > div').forEach(el => {
            if (!seenElements.has(el) && (el.innerText || '').trim().length > 30) {
                seenElements.add(el);
                candidateCards.push(el);
            }
        });

        // Strategy C: Ancestors of post links
        document.querySelectorAll('a[href]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (isPostLink(href)) {
                let parent = a.parentElement;
                let depth = 0;
                let chosen = null;
                while (parent && depth < 12 && parent !== document.body) {
                    if (parent.getAttribute('role') === 'article') {
                        chosen = parent;
                        break;
                    }
                    if (parent.parentElement && parent.parentElement.getAttribute('role') === 'feed') {
                        chosen = parent;
                        break;
                    }
                    const len = (parent.innerText || '').length;
                    if (len > 40 && len < 8000 && !chosen) {
                        chosen = parent;
                    }
                    parent = parent.parentElement;
                    depth++;
                }
                if (chosen && !seenElements.has(chosen)) {
                    seenElements.add(chosen);
                    candidateCards.push(chosen);
                }
            }
        });

        // Strategy D: Fallback to main text blocks
        if (candidateCards.length === 0) {
            document.querySelectorAll('div[role="main"] div[dir="auto"]').forEach(el => {
                let p = el.parentElement;
                let depth = 0;
                while (p && depth < 8 && p !== document.body) {
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

            const allLinks = Array.from(card.querySelectorAll('a[href]'));
            let postUrl = '';
            for (const a of allLinks) {
                if (a.closest('ul') || a.closest('div[aria-label*="bình luận"]') || a.closest('div[aria-label*="Comment"]')) {
                    continue;
                }
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

            if (!postUrl) {
                const groupMatch = window.location.pathname.match(/\/groups\/([^\/]+)/);
                if (groupMatch) {
                    const sampleText = (card.innerText || '').slice(0, 100).replace(/\s+/g, '');
                    let hash = 0;
                    for (let i = 0; i < sampleText.length; i++) {
                        hash = (hash << 5) - hash + sampleText.charCodeAt(i);
                        hash |= 0;
                    }
                    postUrl = `https://www.facebook.com/groups/${groupMatch[1]}/#post_${Math.abs(hash).toString(36)}`;
                }
            }

            if (!postUrl) {
                continue;
            }

            if (seenUrls.has(postUrl)) {
                continue;
            }

            // Extract message content ONLY from main post body (ignoring comments)
            let content = '';
            const msgEls = card.querySelectorAll('div[data-ad-preview="message"], div[dir="auto"]');
            const validSegments = [];

            msgEls.forEach(m => {
                if (m.closest('ul') || m.closest('div[aria-label*="bình luận"]') || m.closest('div[aria-label*="Comment"]')) {
                    return;
                }
                const t = (m.innerText || '').trim();
                if (t.length > 15 && !validSegments.some(s => s.includes(t) || t.includes(s))) {
                    validSegments.push(t);
                }
            });

            if (validSegments.length > 0) {
                content = validSegments.join('\\n\\n');
            }

            if (!content || content.length < 15) {
                const rawText = (card.innerText || '').trim();
                const lines = rawText.split('\\n').map(l => l.trim()).filter(Boolean);
                const filtered = lines.filter(l => {
                    const lower = l.toLowerCase();
                    return !(
                        lower === 'thích' || lower === 'like' ||
                        lower === 'bình luận' || lower === 'comment' ||
                        lower === 'chia sẻ' || lower === 'share' ||
                        lower.startsWith('viết bình luận') ||
                        lower.startsWith('xem thêm bình luận')
                    );
                });
                content = filtered.join('\\n');
            }

            if (!content || content.length < 15) {
                continue;
            }

            seenUrls.add(postUrl);

            // Extract author from header
            let author = 'Facebook User';
            const heading = card.querySelector('h2 a, h3 a, h4 a, strong a, a[role="link"] strong, span[dir="auto"] strong');
            if (heading && (heading.innerText || '').trim()) {
                author = heading.innerText.trim();
            }

            // Extract time
            let rawTime = '';
            const timeEl = card.querySelector('time[datetime]');
            if (timeEl) {
                rawTime = timeEl.getAttribute('datetime') || '';
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

    def collect_posts(self, source_id: str, limit: int = 100) -> list[FacebookPost]:
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
                logger.info(f"Navigating directly to group/page URL: {group_url}")
                try:
                    driver.get(group_url)
                    time.sleep(5)
                except TimeoutException:
                    driver.execute_script("window.stop();")
                logger.info(f"Loaded page/group feed successfully: {driver.title!r}. Extracting raw post data...")
            else:
                # Search directly via top search bar on Facebook homepage when no URL is provided
                self._search_via_ui(driver, search_keyword)

            time.sleep(random.uniform(*self.sleep_range))

            # Smart multi-container scrolling
            scroll_count = max(self.scrolls, 6)
            logger.info(f"Scrolling {scroll_count} times to load dynamic feed content...")
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
                logger.info(f"Scroll {scroll_idx + 1}/{scroll_count} completed. Waiting for posts...")
                time.sleep(random.uniform(*self.sleep_range))

            logger.info("Extracting candidate posts from rendered DOM...")
            raw_posts = self._extract_posts_js(driver, limit=limit)
            logger.info(f"JavaScript post extractor retrieved {len(raw_posts)} candidate post(s).")

            seen_urls: set[str] = set()
            for item in raw_posts:
                if len(posts) >= limit:
                    break
                content = (item.get("content") or "").strip()
                post_url = item.get("post_url") or ""
                author = item.get("author") or "Facebook User"
                raw_time = item.get("raw_time") or ""

                if not content or post_url in seen_urls:
                    continue
                seen_urls.add(post_url)

                post_id = hashlib.sha1(post_url.encode("utf-8")).hexdigest()
                posts.append(
                    FacebookPost(
                        post_id=post_id,
                        group_name="Facebook Search" if not group_url else group_url,
                        content=content,
                        author=author,
                        post_time=self._parse_time(raw_time),
                        post_url=post_url,
                    )
                )

        finally:
            if self._owns_driver:
                driver.quit()

        logger.info(f"Collected {len(posts)} post(s) from Facebook.")
        return posts