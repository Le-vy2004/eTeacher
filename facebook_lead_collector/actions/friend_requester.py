"""Automated Facebook friend request sender for qualified tutoring leads."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import random
import re
import sys
import time
from typing import Any

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from collectors.selenium_facebook import SeleniumFacebookSearchCollector
from config import get_settings
from database.sqlite_db import get_leads_needing_friend_request, update_lead_friend_status
from sheets.google_sheets import GoogleSheetsClient
from utils.logger import logger


def is_anonymous_account(author_name: str, post_url: str = "") -> bool:
    """Detect if an author is an anonymous Facebook participant or group-generated pseudonym."""
    if not author_name:
        return True

    name_clean = author_name.strip()
    low = name_clean.lower()

    # 1. Keywords denoting anonymous participation
    anon_keywords = [
        "ẩn danh",
        "an danh",
        "anonymous",
        "facebook user",
        "người dùng facebook",
        "thành viên ẩn danh",
        "người tham gia ẩn danh",
        "thành viên giấu tên",
        "unknown",
    ]
    if any(k in low for k in anon_keywords):
        return True

    # 2. Facebook generated anonymous animal/word names in groups
    # Pattern: PascalCase words ending in 2 or more digits
    # Examples: ElegantGoose3365, LovelyRaccoon4007, GrayPeapod3778, DecisiveWolf5241, FearlessLynx171
    if re.match(r"^[A-Z][a-z]+(?:[A-Z][a-z]+)*\d{2,}$", name_clean):
        return True

    return False


class FriendRequester:
    """Automates sending Facebook friend requests with rate-limiting and anti-checkpoint delays."""

    def __init__(
        self,
        driver: Any | None = None,
        profile_name: str | None = None,
        min_delay: float = 15.0,
        max_delay: float = 30.0,
        max_requests: int = 15,
    ):
        settings = get_settings()
        self.profile_name = profile_name or settings.chrome_profile_name
        self.min_delay = max(5.0, min_delay)
        self.max_delay = max(self.min_delay, max_delay)
        self.max_requests = max_requests
        self._driver = driver
        self._owns_driver = driver is None

    def _get_driver(self) -> Any:
        if self._driver is None:
            logger.info(f"Initializing Chrome session for Profile '{self.profile_name}'...")
            collector = SeleniumFacebookSearchCollector(profile_name=self.profile_name)
            self._driver = collector._build_driver()
            self._owns_driver = True
        return self._driver

    def close(self) -> None:
        """Close browser if owned by this instance."""
        if self._owns_driver and self._driver is not None:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def _resolve_author_profile_url(self, post_url: str, author_name: str) -> str | None:
        """Resolve the author's profile URL either directly or by inspecting the post page."""
        clean_url = (post_url or "").strip()
        if not clean_url:
            return None

        # Case 1: URL is already a direct user profile or member URL
        if "/user/" in clean_url or "profile.php" in clean_url:
            return clean_url

        # Check if it's a vanity username URL (e.g. facebook.com/username) without post indicators
        if not any(x in clean_url for x in ("/posts/", "/permalink/", "story_fbid=", "multi_permalinks=")):
            return clean_url

        # Case 2: Post URL - navigate to the post and find the author's profile link
        driver = self._get_driver()
        logger.info(f"Navigating to post to find author '{author_name}': {clean_url}")
        try:
            driver.get(clean_url)
            time.sleep(3.5)

            # JavaScript snippet to locate author profile link
            js_script = """
            const authorName = (arguments[0] || '').toLowerCase().trim();
            const cleanAuthor = authorName.replace(/[^a-z0-9àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/gi, ' ');
            
            // Look for anchor links inside post headers
            const candidates = Array.from(document.querySelectorAll(
                'h2 a, h3 a, h4 a, strong a, div[role="article"] a[role="link"], a[href*="/user/"], a[href*="profile.php"]'
            ));
            
            for (const a of candidates) {
                const text = (a.innerText || '').toLowerCase().trim();
                const href = a.getAttribute('href') || a.href || '';
                if (!href || href.includes('/hashtag/') || href.includes('#')) continue;
                
                // If author name matches
                if (authorName && (text.includes(authorName) || (cleanAuthor && text.includes(cleanAuthor)))) {
                    return a.href;
                }
                // Check if link matches group member pattern
                if (href.includes('/user/')) {
                    return a.href;
                }
            }
            
            // Fallback: the first prominent profile-like link in the main article header
            const mainHeader = document.querySelector('div[role="article"] h2 a, div[role="article"] h3 a, div[role="article"] h4 a');
            if (mainHeader && mainHeader.href && !mainHeader.href.includes('/hashtag/')) {
                return mainHeader.href;
            }
            return null;
            """
            found_url = driver.execute_script(js_script, author_name)
            if found_url:
                logger.info(f"Located profile URL for '{author_name}': {found_url}")
                return found_url

        except Exception as e:
            logger.warning(f"Error extracting profile link from post {clean_url}: {e}")

        return None

    def send_friend_request(self, target_url: str, author_name: str) -> tuple[str, str]:
        """Check if author is real, visit their profile, verify friendship status, and click Add Friend.

        Returns:
            tuple of (status_code, description)
            where status_code can be:
            - 'Đã gửi kết bạn'
            - 'Đã là bạn bè'
            - 'Đã gửi trước đó'
            - 'Tài khoản ẩn danh (Bỏ qua)'
            - 'Không mở kết bạn (Chỉ theo dõi)'
            - 'Không tìm thấy trang cá nhân'
            - 'Lỗi kết bạn'
        """
        # Step 0: Check and skip anonymous accounts immediately
        if is_anonymous_account(author_name, target_url):
            logger.info(f"⏭️ Phát hiện tài khoản ẩn danh '{author_name}'. Bỏ qua không gửi kết bạn.")
            return ("Tài khoản ẩn danh (Bỏ qua)", f"Tài khoản '{author_name}' là thành viên ẩn danh Facebook.")

        driver = self._get_driver()

        # Step 1: Resolve profile URL
        profile_url = self._resolve_author_profile_url(target_url, author_name)
        if not profile_url:
            return ("Không tìm thấy trang cá nhân", "Không thể xác định đường link trang cá nhân của tác giả.")

        logger.info(f"Visiting author profile: {profile_url} ({author_name})")
        try:
            driver.get(profile_url)
            time.sleep(random.uniform(3.5, 5.0))

            # If page is still on group member preview, check if there is a 'Xem trang cá nhân' link
            try:
                view_profile_link = driver.execute_script("""
                    const v = document.querySelector('a[href*="profile.php"], a[aria-label*="trang cá nhân"]');
                    if (v && v.href && !v.href.includes('/groups/')) return v.href;
                    return null;
                """)
                if view_profile_link and "profile.php" in view_profile_link:
                    logger.info(f"Navigating to direct personal profile: {view_profile_link}")
                    driver.get(view_profile_link)
                    time.sleep(3.5)
            except Exception:
                pass

            # Step 2: Natural human-like behavior (scroll slightly)
            try:
                driver.execute_script("window.scrollBy(0, 250);")
                time.sleep(0.8)
                driver.execute_script("window.scrollBy(0, -100);")
                time.sleep(0.8)
            except Exception:
                pass

            # Step 3: Precise button inspection with client JavaScript
            js_action = """
            return (function() {
                // Ignore left navigation sidebar elements (href contains '/friends/')
                const isSidebarOrNav = (el) => {
                    const href = (el.getAttribute('href') || el.href || '').toLowerCase();
                    if (href.includes('/friends/') || href.includes('/watch/') || href.includes('/marketplace/')) return true;
                    if (el.closest('div[role="navigation"]')) return true;
                    return false;
                };

                // Collect interactive elements on profile header
                const elements = Array.from(document.querySelectorAll(
                    'div[role="button"], span[role="button"], a[role="button"], button'
                )).filter(el => !isSidebarOrNav(el));

                function getClean(el) {
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase().trim();
                    const text = (el.innerText || el.textContent || '').toLowerCase().trim();
                    const rawAria = (el.getAttribute('aria-label') || '').trim();
                    const rawText = (el.innerText || el.textContent || '').trim();
                    return { el, aria, text, rawAria, rawText };
                }

                const items = elements.map(getClean).filter(b => b.aria || b.text);

                // PRIORITY 1: Look for "Thêm bạn bè" / "Add friend" / "Kết bạn với..."
                for (const b of items) {
                    const isAddFriend = (
                        b.text === 'thêm bạn bè' || b.text === 'thêm bạn' || b.text === 'add friend' ||
                        b.aria.startsWith('thêm bạn') || b.aria.startsWith('kết bạn') || b.aria.startsWith('add friend') ||
                        (b.text.includes('thêm bạn bè') && !b.text.includes('nhóm') && !b.text.includes('bài viết')) ||
                        (b.aria.includes('thêm bạn') && !b.aria.includes('nhóm') && !b.aria.includes('bài viết')) ||
                        (b.aria.includes('kết bạn với') && !b.aria.includes('nhóm'))
                    );
                    if (isAddFriend) {
                        b.el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        b.el.click();
                        return { status: 'CLICKED', reason: b.rawText || b.rawAria };
                    }
                }

                // PRIORITY 2: Look for Already Sent Request ("Hủy lời mời", "Cancel request", "Đã gửi lời mời")
                for (const b of items) {
                    const isSent = (
                        b.text.includes('hủy lời mời') || b.aria.includes('hủy lời mời') ||
                        b.text.includes('đã gửi lời mời') || b.aria.includes('đã gửi lời mời') ||
                        b.text.includes('cancel request') || b.aria.includes('cancel request')
                    );
                    if (isSent) {
                        return { status: 'Đã gửi trước đó', reason: b.rawText || b.rawAria };
                    }
                }

                // PRIORITY 3: Look for Already Friends ("Bạn bè", "Friends")
                // Strict check: standalone button, NOT "/friends/" link, NOT containing "thêm" or "tìm"
                for (const b of items) {
                    const isExactFriend = (
                        (b.text === 'bạn bè' || b.aria === 'bạn bè' || b.text === 'friends' || b.aria === 'friends') &&
                        !b.text.includes('thêm') && !b.aria.includes('thêm') &&
                        !b.text.includes('tìm') && !b.aria.includes('tìm') &&
                        !b.text.includes('cài đặt') && !b.aria.includes('cài đặt') &&
                        !b.text.includes('gợi ý') && !b.aria.includes('gợi ý')
                    );
                    if (isExactFriend) {
                        return { status: 'Đã là bạn bè', reason: b.rawText || b.rawAria };
                    }
                }

                // PRIORITY 4: Check if profile only allows Follow or Message
                const hasFollowOrMsg = items.some(b => 
                    b.text.includes('nhắn tin') || b.aria.includes('nhắn tin') ||
                    b.text.includes('theo dõi') || b.aria.includes('theo dõi')
                );
                if (hasFollowOrMsg) {
                    return { status: 'Không mở kết bạn (Chỉ theo dõi)', reason: 'Profile chỉ mở Nhắn tin / Theo dõi' };
                }

                return { status: 'Không mở kết bạn (Chỉ theo dõi)', reason: 'Không tìm thấy nút Thêm bạn bè' };
            })();
            """
            result = driver.execute_script(js_action) or {}
            status = result.get("status", "Lỗi kết bạn")
            reason = result.get("reason", "")

            if status == "CLICKED":
                time.sleep(2.5)
                # Confirm modal if any
                try:
                    driver.execute_script("""
                        const confirms = Array.from(document.querySelectorAll('div[role="button"], button'));
                        for (const c of confirms) {
                            const t = (c.innerText || '').toLowerCase().trim();
                            if (t === 'xác nhận' || t === 'đồng ý' || t === 'confirm') {
                                c.click();
                                break;
                            }
                        }
                    """)
                except Exception:
                    pass

                logger.info(f"✅ Đã nhấp nút 'Thêm bạn bè' gửi tới '{author_name}' ({profile_url})")
                return ("Đã gửi kết bạn", f"Thành công nhấp: '{reason}'")

            elif status in ("Đã là bạn bè", "Đã gửi trước đó"):
                logger.info(f"ℹ️ {status} với '{author_name}' ({reason})")
                return (status, f"Trạng thái hiện tại: '{reason}'")

            elif status == "Không mở kết bạn (Chỉ theo dõi)":
                logger.info(f"⚠️ Người dùng '{author_name}' không mở nút kết bạn công khai (chỉ theo dõi/nhắn tin).")
                return (status, "Profile không có nút Thêm bạn bè")

            return (status, reason)

        except Exception as e:
            logger.error(f"❌ Lỗi khi tương tác kết bạn với {profile_url}: {e}")
            return ("Lỗi kết bạn", str(e))

    def run_auto_friend_workflow(
        self,
        limit: int | None = None,
        use_sheets: bool = True,
    ) -> dict[str, int]:
        """Execute the automated batch friend requesting workflow."""
        actual_limit = limit or self.max_requests
        stats = {
            "processed": 0,
            "sent": 0,
            "already_friends": 0,
            "already_requested": 0,
            "anonymous_skipped": 0,
            "restricted": 0,
            "errors": 0,
        }

        # Step 1: Collect candidates
        sheets_client: GoogleSheetsClient | None = None
        candidates: list[dict] = []

        if use_sheets:
            try:
                sheets_client = GoogleSheetsClient()
                if sheets_client.connect():
                    candidates = sheets_client.get_leads_to_friend(limit=actual_limit)
                    logger.info(f"Lấy được {len(candidates)} lead cần kết bạn từ Google Sheets.")
            except Exception as e:
                logger.warning(f"Không thể tải danh sách từ Google Sheets: {e}")

        # Fallback to SQLite DB if candidates is empty or sheets not available
        if not candidates:
            candidates = get_leads_needing_friend_request(limit=actual_limit)
            logger.info(f"Lấy được {len(candidates)} lead cần kết bạn từ Database SQLite.")

        if not candidates:
            print("\n[✓] Không có lead nào cần gửi lời mời kết bạn (tất cả đã được xử lý hoặc danh sách trống).")
            return stats

        print("\n" + "=" * 75)
        print(f"🤝 BẮT ĐẦU QUY TRÌNH TỰ ĐỘNG GỬI LỜI MỜI KẾT BẠN ({len(candidates)} TÀI KHOẢN)")
        print(f"⏱️ Độ trễ an toàn giữa các lần gửi: {self.min_delay:.0f}s - {self.max_delay:.0f}s")
        print("=" * 75 + "\n")

        try:
            for idx, candidate in enumerate(candidates, 1):
                post_url = candidate.get("post_url", "")
                author = candidate.get("author", "Unknown")
                row_number = candidate.get("row_number")

                print(f"[{idx}/{len(candidates)}] Đang xử lý: {author} | {post_url}")

                status, detail = self.send_friend_request(post_url, author)
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Update in Google Sheets if available
                if sheets_client and sheets_client.is_connected and row_number:
                    try:
                        sheets_client.update_friend_status(row_number, status, now_str)
                    except Exception as e:
                        logger.warning(f"Không thể cập nhật Google Sheets dòng {row_number}: {e}")

                # Update in SQLite DB
                update_lead_friend_status(post_url, status, now_str)

                # Update stats
                stats["processed"] += 1
                if status == "Đã gửi kết bạn":
                    stats["sent"] += 1
                    print(f"   👉 KẾT QUẢ: ✅ {status} ({detail})")
                elif status == "Tài khoản ẩn danh (Bỏ qua)":
                    stats["anonymous_skipped"] += 1
                    print(f"   👉 KẾT QUẢ: ⏭️ {status}")
                elif status == "Đã là bạn bè":
                    stats["already_friends"] += 1
                    print(f"   👉 KẾT QUẢ: 👫 {status}")
                elif status == "Đã gửi trước đó":
                    stats["already_requested"] += 1
                    print(f"   👉 KẾT QUẢ: ⏳ {status}")
                elif status == "Không mở kết bạn (Chỉ theo dõi)":
                    stats["restricted"] += 1
                    print(f"   👉 KẾT QUẢ: 🔒 {status}")
                else:
                    stats["errors"] += 1
                    print(f"   👉 KẾT QUẢ: ❌ {status} ({detail})")

                # Delay before next request (if not anonymous and not last candidate)
                if idx < len(candidates):
                    if status == "Tài khoản ẩn danh (Bỏ qua)":
                        time.sleep(0.5)
                    else:
                        sleep_time = random.uniform(self.min_delay, self.max_delay)
                        print(f"   ⏳ Nghỉ an toàn {sleep_time:.1f} giây chống Facebook Checkpoint...\n")
                        time.sleep(sleep_time)

        finally:
            self.close()

        print("\n" + "=" * 75)
        print("📊 TỔNG KẾT QUY TRÌNH GỬI LỜI MỜI KẾT BẠN:")
        print(f" - Tổng số tài khoản đã xử lý: {stats['processed']}")
        print(f" - Gửi thành công: {stats['sent']}")
        print(f" - Bỏ qua tài khoản ẩn danh: {stats['anonymous_skipped']}")
        print(f" - Đã là bạn bè từ trước: {stats['already_friends']}")
        print(f" - Đã gửi lời mời trước đó: {stats['already_requested']}")
        print(f" - Không mở nút kết bạn (Chỉ theo dõi): {stats['restricted']}")
        print(f" - Lỗi/Không tìm thấy profile: {stats['errors']}")
        print("=" * 75 + "\n")

        return stats
