"""Live Facebook Graph API post collector."""
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

# Ensure project root is in sys.path when running directly
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from collectors.base import BaseCollector
from config import get_settings
from models.post import FacebookPost
from utils.logger import logger
from utils.text_utils import extract_source_id_from_url


class FacebookCollector(BaseCollector):
    """Collector for Facebook posts using the official Graph API.

    Requires a valid user or page access token with permissions to read group/page feed
    (e.g., groups_access_member_info or pages_read_engagement).
    """

    def __init__(
        self,
        access_token: str | None = None,
        api_base_url: str | None = None,
        timeout: int = 15,
    ):
        settings = get_settings()
        self.access_token = access_token or settings.facebook_access_token
        self.api_base_url = (
            api_base_url or settings.facebook_api_base_url
        ).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _parse_created_time(self, raw_time: str | None) -> datetime:
        """Parse Facebook ISO 8601 timestamp safely."""
        if not raw_time:
            return datetime.now()
        try:
            # Format: '2026-09-18T07:00:00+0000' or '2026-09-18T07:00:00Z'
            clean_time = raw_time.replace("Z", "+00:00")
            return datetime.fromisoformat(clean_time)
        except Exception:
            return datetime.now()

    def collect_posts(
        self,
        source_id: str,
        limit: int = 100,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[FacebookPost]:
        """Fetch posts from a Facebook Group or Page feed.

        Args:
            source_id: Facebook Group ID or Page ID.
            limit: Maximum total posts to retrieve.
            since: Optional lower bound datetime.
            until: Optional upper bound datetime.

        Returns:
            List of FacebookPost objects.

        Raises:
            ValueError: If access token or source_id is missing.
            requests.RequestException: If API request fails.
        """
        if not self.access_token:
            raise ValueError(
                "Facebook access token is missing. Please configure FACEBOOK_ACCESS_TOKEN "
                "in your .env file, pass via --token, or use --mock mode for testing."
            )

        if not source_id:
            raise ValueError("source_id (Group/Page ID or URL) cannot be empty.")

        clean_source_id = extract_source_id_from_url(source_id)
        if not clean_source_id:
            raise ValueError(f"Could not extract a valid Group/Page ID from input: '{source_id}'")

        endpoint = f"{self.api_base_url}/{clean_source_id}/feed"
        fields = "id,message,from,created_time,permalink_url"

        params: dict[str, Any] = {
            "access_token": self.access_token,
            "fields": fields,
            "limit": min(limit, 100),
        }

        if since:
            params["since"] = int(since.timestamp())
        if until:
            params["until"] = int(until.timestamp())

        posts: list[FacebookPost] = []
        next_url: str | None = endpoint
        is_first_page = True

        logger.info(f"Starting Facebook API collection for source '{source_id}' (limit: {limit})")

        try:
            while next_url and len(posts) < limit:
                if is_first_page:
                    resp = self.session.get(
                        next_url,
                        params=params,
                        timeout=self.timeout,
                    )
                    is_first_page = False
                else:
                    # Next pagination URL already contains access_token and parameters
                    resp = self.session.get(next_url, timeout=self.timeout)

                resp.raise_for_status()
                data = resp.json()

                feed_items = data.get("data", [])
                if not feed_items:
                    break

                for item in feed_items:
                    content = item.get("message")
                    # Skip posts without textual content
                    if not content or not content.strip():
                        continue

                    post_id = str(item.get("id", ""))
                    #permalink_url is preferred; fallback to standard web link
                    post_url = item.get("permalink_url") or f"https://www.facebook.com/{post_id}"
                    
                    author_obj = item.get("from", {})
                    author_name = author_obj.get("name") if isinstance(author_obj, dict) else "Unknown"

                    post = FacebookPost(
                        post_id=post_id,
                        group_name=str(source_id),
                        content=content.strip(),
                        author=author_name or "Unknown",
                        post_time=self._parse_created_time(item.get("created_time")),
                        post_url=post_url,
                    )
                    posts.append(post)

                    if len(posts) >= limit:
                        break

                # Handle cursor pagination
                paging = data.get("paging", {})
                next_url = paging.get("next")

        except requests.exceptions.Timeout:
            logger.error(f"Timeout while calling Facebook API endpoint: {endpoint}")
            raise
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None
            error_detail = ""
            try:
                error_detail = e.response.json() if e.response is not None else ""
            except Exception:
                error_detail = e.response.text if e.response is not None else ""
            logger.error(
                f"Facebook API HTTP Error {status_code}: {error_detail}"
            )
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook API Request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Facebook API collection: {e}")
            raise

        logger.info(f"Collected {len(posts)} posts from Facebook API")
        return posts


if __name__ == "__main__":
    import argparse

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Test Facebook Collector with a live URL or ID")
    parser.add_argument("--source", type=str, required=False, help="Facebook Group URL, Page URL, or ID")
    parser.add_argument("--token", type=str, required=False, help="Facebook Graph API Access Token")
    parser.add_argument("--limit", type=int, default=5, help="Number of posts to fetch")
    args = parser.parse_args()

    settings = get_settings()
    token = args.token or settings.facebook_access_token
    source = args.source or settings.facebook_source_id

    print("\n--- Kiểm Tra Kết Nối Facebook Collector ---")
    print(f"API Base URL: {settings.facebook_api_base_url}")
    print(f"Source Input: {source or '[Chưa nhập - dùng cờ --source URL]'}")
    print(f"Token Config: {'Đã có' if token else 'CHƯA CÓ (cần FACEBOOK_ACCESS_TOKEN hoặc --token)'}")

    if not token or not source:
        print("\n[HƯỚNG DẪN TEST VỚI URL FACEBOOK THẬT]:")
        print("1. Lấy User Access Token miễn phí trong 1 phút tại:")
        print("   https://developers.facebook.com/tools/explorer/")
        print("2. Chạy lệnh:")
        print("   python collectors/facebook.py --source \"<FACEBOOK_URL_HOAC_ID>\" --token \"<YOUR_TOKEN>\"\n")
    else:
        try:
            collector = FacebookCollector(access_token=token)
            posts = collector.collect_posts(source_id=source, limit=args.limit)
            print(f"\n[✓] Thành công! Lấy được {len(posts)} bài viết từ Facebook:")
            for idx, p in enumerate(posts, 1):
                print(f"  {idx}. [{p.post_time}] {p.author}: {p.content[:80]}... ({p.post_url})")
        except Exception as e:
            print(f"\n[X] Lỗi khi gọi Facebook API: {e}")
