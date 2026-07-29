"""One-time Facebook browser login for public page scraping.

Opens Chromium so you can log into your personal Facebook account, then
saves the session for headless polling (no Page admin required).

Usage:
  python facebook_login.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from config import ensure_directories
from services.facebook_public import FACEBOOK_STORAGE_STATE


async def _login() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(
            "playwright is not installed.\n"
            "Run: pip install playwright\n"
            "Then: playwright install chromium"
        )
        sys.exit(1)

    ensure_directories()
    FACEBOOK_STORAGE_STATE.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")

        print("Log into Facebook in the opened browser window.")
        print("After your news feed / home page loads, return here and press Enter.")
        await asyncio.to_thread(input, "")

        await context.storage_state(path=str(FACEBOOK_STORAGE_STATE))
        await browser.close()

    path: Path = FACEBOOK_STORAGE_STATE
    print(f"Saved Facebook session to {path}")
    print("You can now set facebook_page_ids (e.g. dimyanmar.org) and run python app.py")


if __name__ == "__main__":
    asyncio.run(_login())
