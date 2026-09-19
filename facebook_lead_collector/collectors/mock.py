"""Mock Facebook Collector for testing and development without live API credentials."""
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Ensure project root is in sys.path when running directly
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from collectors.base import BaseCollector
from models.post import FacebookPost
from utils.logger import logger


class MockFacebookCollector(BaseCollector):
    """Mock collector that returns pre-configured or realistic simulated Facebook posts."""

    def __init__(self, custom_posts: list[FacebookPost] | None = None):
        """Initialize mock collector with optional custom posts for testing.

        Args:
            custom_posts: Optional list of posts to return. If None, default
                          simulated posts are used.
        """
        self.custom_posts = custom_posts

    def _generate_default_posts(self, source_id: str, limit: int) -> list[FacebookPost]:
        """Generate a realistic set of simulated Facebook posts for tutor hunting."""
        now = datetime.now()
        group = f"Cộng Đồng Gia Sư - {source_id or 'Demo Group'}"

        mock_data = [
            # 1. Matching tutor search: Math
            {
                "post_id": "mock_post_001",
                "group_name": group,
                "content": "Phụ huynh cần tìm gia sư toán lớp 8 tại Quận 7, tuần dạy 2 buổi tối.",
                "author": "Nguyễn Văn A",
                "post_time": now - timedelta(minutes=15),
                "post_url": "https://facebook.com/groups/demo/posts/1001",
            },
            # 2. Matching tutor search: English (uppercase test)
            {
                "post_id": "mock_post_002",
                "group_name": group,
                "content": "CẦN GIA SƯ TIẾNG ANH ôn thi chứng chỉ IELTS cho học sinh cấp 3 tại Ba Đình.",
                "author": "Trần Thị B",
                "post_time": now - timedelta(hours=1),
                "post_url": "https://facebook.com/groups/demo/posts/1002",
            },
            # 3. Matching tutor search: Physics & Teacher
            {
                "post_id": "mock_post_003",
                "group_name": group,
                "content": "Gia đình đang cần giáo viên dạy kèm gia sư lý lớp 11 khu vực Cầu Giấy.",
                "author": "Lê Văn C",
                "post_time": now - timedelta(hours=2),
                "post_url": "https://facebook.com/groups/demo/posts/1003",
            },
            # 4. Duplicate post testing: same URL as mock_post_001
            {
                "post_id": "mock_post_004",
                "group_name": group,
                "content": "Phụ huynh cần tìm gia sư toán lớp 8 tại Quận 7, tuần dạy 2 buổi tối. (Đăng lại)",
                "author": "Nguyễn Văn A",
                "post_time": now - timedelta(minutes=5),
                "post_url": "https://facebook.com/groups/demo/posts/1001",
            },
            # 5. Non-matching post: selling books
            {
                "post_id": "mock_post_005",
                "group_name": group,
                "content": "Thanh lý bộ sách giáo khoa lớp 10 và máy tính Casio 580 còn mới 95%.",
                "author": "Hoàng Thị D",
                "post_time": now - timedelta(hours=3),
                "post_url": "https://facebook.com/groups/demo/posts/1005",
            },
            # 6. Non-matching post: tutor offering services (not finding tutor)
            {
                "post_id": "mock_post_006",
                "group_name": group,
                "content": "Hôm nay trời đẹp, chúc các bạn học sinh ôn thi đạt kết quả tốt nhất!",
                "author": "Phạm Văn E",
                "post_time": now - timedelta(hours=4),
                "post_url": "https://facebook.com/groups/demo/posts/1006",
            },
            # 7. Matching tutor search: Chemistry
            {
                "post_id": "mock_post_007",
                "group_name": group,
                "content": "Mình cần tìm gia sư hóa lớp 9 cấp tốc chuẩn bị thi vào 10 chuyên.",
                "author": "Vũ Minh F",
                "post_time": now - timedelta(hours=5),
                "post_url": "https://facebook.com/groups/demo/posts/1007",
            },
            # 8. Matching tutor search: Literature
            {
                "post_id": "mock_post_008",
                "group_name": group,
                "content": "Gia đình cần tìm gia sư văn lớp 12 luyện thi đại học tại Quận 1.",
                "author": "Đặng Thu G",
                "post_time": now - timedelta(hours=6),
                "post_url": "https://facebook.com/groups/demo/posts/1008",
            },
        ]

        posts: list[FacebookPost] = []
        for item in mock_data[:limit]:
            posts.append(FacebookPost(**item))
        return posts

    def collect_posts(self, source_id: str, limit: int = 100) -> list[FacebookPost]:
        """Return simulated Facebook posts.

        Args:
            source_id: Identifier for mock group or source.
            limit: Maximum posts to return.

        Returns:
            List of FacebookPost objects.
        """
        logger.info(f"MockCollector starting simulation for source: '{source_id or 'default_mock'}'")
        if self.custom_posts is not None:
            posts = self.custom_posts[:limit]
        else:
            posts = self._generate_default_posts(source_id, limit)

        logger.info(f"MockCollector generated {len(posts)} posts")
        return posts
