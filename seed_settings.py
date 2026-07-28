"""Create/update app_settings in Neon.

Usage:
  python seed_settings.py --api-id 123 --api-hash abc --channels dimyanmarexchange
  python seed_settings.py   # also accepts values from leftover .env keys while migrating
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from config import BASE_DIR, get_database_url
from db import upsert_settings


def main() -> None:
    load_dotenv(BASE_DIR / ".env")

    parser = argparse.ArgumentParser(description="Seed Neon app_settings")
    parser.add_argument("--api-id", type=int, default=None)
    parser.add_argument("--api-hash", default=None)
    parser.add_argument(
        "--channels",
        default=None,
        help="Comma-separated Telegram channel usernames",
    )
    parser.add_argument("--facebook-token", default=None)
    parser.add_argument(
        "--facebook-pages",
        default=None,
        help="Comma-separated Facebook page IDs/usernames",
    )
    parser.add_argument("--poll-interval", type=int, default=None)
    args = parser.parse_args()

    api_id_raw: str | None = (
        str(args.api_id) if args.api_id is not None else os.getenv("API_ID")
    )
    api_hash: str | None = args.api_hash or os.getenv("API_HASH")
    channels: str | None = args.channels or os.getenv("CHANNEL_USERNAME")
    facebook_token: str = (
        args.facebook_token
        if args.facebook_token is not None
        else (os.getenv("FACEBOOK_ACCESS_TOKEN") or "")
    ).strip()
    facebook_pages: str = (
        args.facebook_pages
        if args.facebook_pages is not None
        else (os.getenv("FACEBOOK_PAGE_IDS") or "")
    ).strip()
    poll_raw: str = str(
        args.poll_interval
        if args.poll_interval is not None
        else (os.getenv("FACEBOOK_POLL_INTERVAL_SECONDS") or "300")
    )

    if not api_id_raw or not api_hash or not channels:
        print(
            "Error: api_id, api_hash, and channels are required "
            "(via CLI flags or temporary .env keys)."
        )
        sys.exit(1)

    try:
        api_id: int = int(api_id_raw)
        poll_interval: int = int(poll_raw)
        database_url: str = get_database_url()
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    upsert_settings(
        database_url,
        api_id=api_id,
        api_hash=api_hash,
        channel_usernames=channels,
        facebook_access_token=facebook_token or None,
        facebook_page_ids=facebook_pages or None,
        facebook_poll_interval_seconds=poll_interval,
    )
    print("app_settings saved to Neon successfully.")


if __name__ == "__main__":
    main()
