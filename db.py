"""PostgreSQL (Neon) access for application settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    api_id INTEGER NOT NULL,
    api_hash TEXT NOT NULL,
    channel_usernames TEXT NOT NULL,
    facebook_access_token TEXT,
    facebook_page_ids TEXT,
    facebook_poll_interval_seconds INTEGER NOT NULL DEFAULT 300,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


@dataclass(frozen=True)
class SettingsRow:
    """One row from app_settings."""

    api_id: int
    api_hash: str
    channel_usernames: str
    facebook_access_token: str | None
    facebook_page_ids: str | None
    facebook_poll_interval_seconds: int


def connect(database_url: str) -> psycopg.Connection[Any]:
    """Open a PostgreSQL connection."""
    return psycopg.connect(database_url, row_factory=dict_row)


def ensure_schema(database_url: str) -> None:
    """Create app_settings if it does not exist."""
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


def fetch_settings(database_url: str) -> SettingsRow | None:
    """Load the singleton settings row, or None if missing."""
    ensure_schema(database_url)
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    api_id,
                    api_hash,
                    channel_usernames,
                    facebook_access_token,
                    facebook_page_ids,
                    facebook_poll_interval_seconds
                FROM app_settings
                WHERE id = 1
                """
            )
            row = cur.fetchone()
    if row is None:
        return None
    return SettingsRow(
        api_id=int(row["api_id"]),
        api_hash=str(row["api_hash"]),
        channel_usernames=str(row["channel_usernames"]),
        facebook_access_token=(
            str(row["facebook_access_token"])
            if row["facebook_access_token"]
            else None
        ),
        facebook_page_ids=(
            str(row["facebook_page_ids"]) if row["facebook_page_ids"] else None
        ),
        facebook_poll_interval_seconds=int(row["facebook_poll_interval_seconds"]),
    )


def upsert_settings(
    database_url: str,
    *,
    api_id: int,
    api_hash: str,
    channel_usernames: str,
    facebook_access_token: str | None = None,
    facebook_page_ids: str | None = None,
    facebook_poll_interval_seconds: int = 300,
) -> None:
    """Insert or update the singleton settings row."""
    ensure_schema(database_url)
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_settings (
                    id,
                    api_id,
                    api_hash,
                    channel_usernames,
                    facebook_access_token,
                    facebook_page_ids,
                    facebook_poll_interval_seconds,
                    updated_at
                ) VALUES (
                    1, %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    api_id = EXCLUDED.api_id,
                    api_hash = EXCLUDED.api_hash,
                    channel_usernames = EXCLUDED.channel_usernames,
                    facebook_access_token = EXCLUDED.facebook_access_token,
                    facebook_page_ids = EXCLUDED.facebook_page_ids,
                    facebook_poll_interval_seconds = EXCLUDED.facebook_poll_interval_seconds,
                    updated_at = NOW()
                """,
                (
                    api_id,
                    api_hash,
                    channel_usernames,
                    facebook_access_token,
                    facebook_page_ids,
                    facebook_poll_interval_seconds,
                ),
            )
        conn.commit()
