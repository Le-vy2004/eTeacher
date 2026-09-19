"""Abstract base class for Facebook post collectors."""
from abc import ABC, abstractmethod
from models.post import FacebookPost


class BaseCollector(ABC):
    """Abstract interface defining the contract for post collectors."""

    @abstractmethod
    def collect_posts(
        self,
        source_id: str,
        limit: int = 100,
    ) -> list[FacebookPost]:
        """Fetch posts from the given source or group identifier.

        Args:
            source_id: Facebook group ID, page ID, or mock source identifier.
            limit: Maximum number of posts to retrieve.

        Returns:
            List of FacebookPost objects.

        Raises:
            Exception: If an unrecoverable collection error occurs.
        """
        pass
