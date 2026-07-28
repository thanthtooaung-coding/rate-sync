"""Application configuration loaded from Neon PostgreSQL."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from db import SettingsRow, fetch_settings

BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
SESSION_DIR: Path = BASE_DIR / "session"
LOGS_DIR: Path = BASE_DIR / "logs"

EXCEL_PATH: Path = DATA_DIR / "exchange.xlsx"
SESSION_PATH: Path = SESSION_DIR / "telegram"
LOG_PATH: Path = LOGS_DIR / "app.log"

HISTORICAL_MESSAGE_LIMIT: int = 100
DEFAULT_FACEBOOK_POLL_INTERVAL_SECONDS: int = 300


@dataclass(frozen=True)
class Settings:
    """Runtime settings sourced from the database."""

    api_id: int
    api_hash: str
    channel_usernames: tuple[str, ...]
    facebook_access_token: str | None
    facebook_page_ids: tuple[str, ...]
    facebook_poll_interval_seconds: int

    @property
    def facebook_enabled(self) -> bool:
        """Return True when Facebook token and page IDs are configured."""
        return bool(self.facebook_access_token and self.facebook_page_ids)


def _parse_list(raw: str | None) -> tuple[str, ...]:
    """Parse a comma/semicolon-separated list of identifiers."""
    if not raw:
        return ()
    parts: list[str] = []
    seen: set[str] = set()
    for token in raw.replace(";", ",").split(","):
        value: str = token.strip().lstrip("@")
        if not value:
            continue
        key: str = value.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(value)
    return tuple(parts)


def get_database_url() -> str:
    """Load DATABASE_URL from .env."""
    load_dotenv(BASE_DIR / ".env")
    database_url: str | None = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required in .env")
    return database_url


def load_settings() -> Settings:
    """Load and validate settings from Neon PostgreSQL.

    Returns:
        Validated application settings.

    Raises:
        ValueError: If DATABASE_URL is missing or settings row is invalid/absent.
    """
    database_url: str = get_database_url()
    row: SettingsRow | None = fetch_settings(database_url)
    if row is None:
        raise ValueError(
            "No settings found in database. Run: python seed_settings.py"
        )

    channels: tuple[str, ...] = _parse_list(row.channel_usernames)
    if not channels:
        raise ValueError("channel_usernames in app_settings must not be empty")

    facebook_token: str | None = (
        row.facebook_access_token.strip() if row.facebook_access_token else None
    )
    facebook_pages: tuple[str, ...] = _parse_list(row.facebook_page_ids)
    poll_interval: int = row.facebook_poll_interval_seconds or (
        DEFAULT_FACEBOOK_POLL_INTERVAL_SECONDS
    )
    if poll_interval < 30:
        raise ValueError("facebook_poll_interval_seconds must be at least 30")

    if bool(facebook_token) ^ bool(facebook_pages):
        raise ValueError(
            "Facebook requires both facebook_access_token and facebook_page_ids, "
            "or leave both empty to disable Facebook sync"
        )

    return Settings(
        api_id=row.api_id,
        api_hash=row.api_hash,
        channel_usernames=channels,
        facebook_access_token=facebook_token or None,
        facebook_page_ids=facebook_pages,
        facebook_poll_interval_seconds=poll_interval,
    )


def ensure_directories() -> None:
    """Create required project directories if they do not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
