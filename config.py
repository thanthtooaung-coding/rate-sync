"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
SESSION_DIR: Path = BASE_DIR / "session"
LOGS_DIR: Path = BASE_DIR / "logs"

EXCEL_PATH: Path = DATA_DIR / "exchange.xlsx"
SESSION_PATH: Path = SESSION_DIR / "telegram"
LOG_PATH: Path = LOGS_DIR / "app.log"

HISTORICAL_MESSAGE_LIMIT: int = 100


@dataclass(frozen=True)
class Settings:
    """Runtime settings sourced from .env."""

    api_id: int
    api_hash: str
    channel_usernames: tuple[str, ...]


def _parse_channels(raw: str) -> tuple[str, ...]:
    """Parse a comma/semicolon-separated channel list.

    Args:
        raw: Raw CHANNEL_USERNAME value from .env.

    Returns:
        Deduplicated channel usernames without leading @.
    """
    parts: list[str] = []
    for token in raw.replace(";", ",").split(","):
        channel: str = token.strip().lstrip("@")
        if channel and channel.lower() not in {p.lower() for p in parts}:
            parts.append(channel)
    return tuple(parts)


def load_settings() -> Settings:
    """Load and validate settings from the environment.

    Returns:
        Validated application settings.

    Raises:
        ValueError: If required environment variables are missing or invalid.
    """
    load_dotenv(BASE_DIR / ".env")

    api_id_raw: str | None = os.getenv("API_ID")
    api_hash: str | None = os.getenv("API_HASH")
    channel_raw: str = os.getenv("CHANNEL_USERNAME", "dimyanmarexchange")

    if not api_id_raw:
        raise ValueError("API_ID is required in .env")
    if not api_hash:
        raise ValueError("API_HASH is required in .env")

    try:
        api_id: int = int(api_id_raw)
    except ValueError as exc:
        raise ValueError("API_ID must be an integer") from exc

    channels: tuple[str, ...] = _parse_channels(channel_raw)
    if not channels:
        raise ValueError(
            "CHANNEL_USERNAME is required (comma-separated for multiple channels)"
        )

    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        channel_usernames=channels,
    )


def ensure_directories() -> None:
    """Create required project directories if they do not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
