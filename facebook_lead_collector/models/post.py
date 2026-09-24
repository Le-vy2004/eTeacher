"""Data models for Facebook posts and tutoring leads."""
from datetime import datetime
from pydantic import BaseModel, Field


class FacebookPost(BaseModel):
    """Raw post retrieved from Facebook API or data source.

    Attributes:
        post_id: Unique post identifier from Facebook.
        group_name: Name of the Facebook group where the post appeared.
        content: Text content of the post.
        author: Name or ID of the author who published the post.
        post_time: Publication timestamp of the post.
        post_url: Direct URL linking to the post.
    """

    post_id: str = Field(..., description="Unique post ID from source")
    group_name: str = Field(..., description="Name of the Facebook group")
    content: str = Field(..., description="Full text content of the post")
    author: str = Field(default="Unknown", description="Author name or username")
    post_time: datetime = Field(..., description="Time post was created")
    post_url: str = Field(..., description="Canonical URL to the post")


class Lead(BaseModel):
    """Qualified tutoring lead that matched keyword filter and entity extraction."""

    group_name: str = Field(..., description="Name of the Facebook group")
    keyword: str = Field(..., description="Matched keyword(s), comma-separated")
    author: str = Field(default="Unknown", description="Author of the post")
    post_time: datetime = Field(..., description="Time post was created")
    post_url: str = Field(..., description="Canonical URL to the post")
    content: str = Field(default="", description="Full text content of the post")
    phone: str | None = Field(default=None, description="Normalized 10-digit phone number")
    zalo_url: str | None = Field(default=None, description="Direct Zalo chat URL")
    min_budget: int | None = Field(default=None, description="Minimum budget in VND")
    max_budget: int | None = Field(default=None, description="Maximum budget in VND")
    budget_unit: str | None = Field(default=None, description="Budget unit (buổi, giờ, tháng)")
    subject: str = Field(default="Khác", description="Extracted subject taxonomy")
    grade: str = Field(default="Khác", description="Extracted grade taxonomy")
    lead_type: str = Field(default="Phụ huynh / Học sinh", description="Lead classification type")
    friend_status: str | None = Field(default=None, description="Trạng thái kết bạn Facebook")
    friend_requested_at: datetime | None = Field(default=None, description="Thời gian gửi lời mời")
    collected_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when lead was collected",
    )

    def format_budget_display(self) -> str:
        """Format budget range for readable display."""
        if not self.min_budget and not self.max_budget:
            return "Thỏa thuận"
        unit_str = f"/{self.budget_unit}" if self.budget_unit else ""
        if self.min_budget == self.max_budget:
            return f"{self.min_budget:,}đ{unit_str}"
        return f"{self.min_budget:,}đ - {self.max_budget:,}đ{unit_str}"

    def to_sheet_row(self, formula_sep: str = ";") -> list[str]:
        """Format lead as a row for Google Sheets matching expanded column requirements."""
        post_time_formatted = (
            self.post_time.strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(self.post_time, datetime)
            else str(self.post_time)
        )
        zalo_formula = f'=HYPERLINK("{self.zalo_url}"{formula_sep} "💬 Chat Zalo")' if self.zalo_url else "Không có SĐT"
        fb_link_formula = f'=HYPERLINK("{self.post_url}"{formula_sep} "🔗 Xem bài viết")'
        friend_req_time = (
            self.friend_requested_at.strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(self.friend_requested_at, datetime)
            else (str(self.friend_requested_at) if self.friend_requested_at else "")
        )

        return [
            zalo_formula,
            self.phone or "",
            self.subject,
            self.grade,
            self.format_budget_display(),
            fb_link_formula,
            self.author,
            post_time_formatted,
            self.content,
            self.group_name,
            self.keyword,
            self.collected_at.strftime("%Y-%m-%d %H:%M:%S"),
            self.lead_type,
            self.friend_status or "",
            friend_req_time,
        ]


