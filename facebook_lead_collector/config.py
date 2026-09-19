"""Configuration management using python-dotenv and Pydantic."""
from functools import lru_cache
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Base directory for the project
BASE_DIR = Path(__file__).resolve().parent

# Load .env if present
load_dotenv(dotenv_path=BASE_DIR / ".env")


class Settings(BaseModel):
    """Application settings and environment configurations."""

    # Facebook API
    facebook_access_token: str = Field(
        default_factory=lambda: os.getenv("FACEBOOK_ACCESS_TOKEN", "").strip()
    )
    facebook_api_base_url: str = Field(
        default_factory=lambda: os.getenv(
            "FACEBOOK_API_BASE_URL", "https://graph.facebook.com/v19.0"
        ).rstrip("/")
    )
    facebook_source_id: str = Field(
        default_factory=lambda: os.getenv("FACEBOOK_SOURCE_ID", "").strip()
    )

    # Google Sheets
    google_credentials_file: str = Field(
        default_factory=lambda: os.getenv(
            "GOOGLE_CREDENTIALS_FILE", "service_account.json"
        ).strip()
    )
    google_sheet_name: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_SHEET_NAME", "Facebook Leads").strip()
    )
    google_worksheet_name: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_WORKSHEET_NAME", "Posts").strip()
    )

    # Database
    database_path: str = Field(
        default_factory=lambda: os.getenv("DATABASE_PATH", "data/leads.db").strip()
    )

    # Collector parameters
    collector_limit: int = Field(
        default_factory=lambda: int(os.getenv("COLLECTOR_LIMIT", "100"))
    )
    log_level: str = Field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper()
    )

    @property
    def resolved_database_path(self) -> Path:
        """Resolve database path relative to project root if not absolute."""
        db_path = Path(self.database_path)
        if not db_path.is_absolute():
            db_path = BASE_DIR / db_path
        return db_path

    @property
    def resolved_google_credentials_path(self) -> Path:
        """Resolve Google credentials file path relative to project root."""
        cred_path = Path(self.google_credentials_file)
        if not cred_path.is_absolute():
            cred_path = BASE_DIR / cred_path
        return cred_path

    @property
    def has_facebook_credentials(self) -> bool:
        """Check if required Facebook API credentials are provided."""
        return bool(self.facebook_access_token)

    @property
    def has_google_credentials(self) -> bool:
        """Check if Google service account credentials file exists."""
        return self.resolved_google_credentials_path.is_file()


@lru_cache
def get_settings() -> Settings:
    """Get singleton instance of application settings."""
    return Settings()
