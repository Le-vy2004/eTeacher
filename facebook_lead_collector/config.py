"""Configuration management using python-dotenv and Pydantic."""
from functools import lru_cache
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Base directory for the project
BASE_DIR = Path(__file__).resolve().parent


def _default_chrome_user_data() -> str:
    """Return the standard Chrome user-data directory on the current OS."""
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return str(Path(local_app_data) / "Google" / "Chrome" / "User Data")
    return str(Path.home() / ".config" / "google-chrome")


def _default_chrome_profile() -> str:
    """Use Chrome's last selected profile when its Local State is available."""
    user_data = Path(_default_chrome_user_data())
    local_state = user_data / "Local State"
    try:
        with local_state.open("r", encoding="utf-8") as file:
            profile = json.load(file).get("profile", {}).get("last_used")
            if profile:
                return str(profile)
    except (OSError, ValueError, TypeError):
        pass
    return "Default"

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
    facebook_group_url: str = Field(
        default_factory=lambda: os.getenv("FACEBOOK_GROUP_URL", "").strip()
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

    # Selenium local Chrome profile
    chrome_user_data: str = Field(
        default_factory=lambda: os.getenv(
            "CHROME_USER_DATA", _default_chrome_user_data()
        ).strip()
    )
    chrome_profile_name: str = Field(
        default_factory=lambda: os.getenv(
            "PROFILE_NAME", _default_chrome_profile()
        ).strip()
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
