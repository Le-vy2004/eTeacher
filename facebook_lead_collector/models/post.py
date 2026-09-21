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
    """Qualified tutoring lead that matched keyword filter.

    Attributes:
        group_name: Name of the Facebook group where the post was found.
        keyword: Matched keyword(s), separated by comma if multiple.
        author: Author of the post.
        post_time: Publication timestamp of the post.
        post_url: Unique URL to the post.
        content: Text content of the post.
        collected_at: Timestamp when lead was captured by this system.
    """

    group_name: str = Field(..., description="Name of the Facebook group")
    keyword: str = Field(..., description="Matched keyword(s), comma-separated")
    author: str = Field(default="Unknown", description="Author of the post")
    post_time: datetime = Field(..., description="Time post was created")
    post_url: str = Field(..., description="Canonical URL to the post")
    content: str = Field(default="", description="Full text content of the post")
    collected_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when lead was collected",
    )

    def to_sheet_row(self) -> list[str]:
        """Format lead as a row for Google Sheets."""
        return [
            self.group_name,
            self.keyword,
            self.author,
            self.post_time.strftime("%Y-%m-%d %H:%M:%S"),
            self.post_url,
            self.collected_at.strftime("%Y-%m-%d %H:%M:%S"),
            self.content,
        ]
