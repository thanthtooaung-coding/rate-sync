"""Fetch Facebook page posts without Page admin access.

Uses a saved Playwright browser session (normal user login) to open the
public page and extract post text. This is fragile and may break when
Facebook changes their UI; it is not an official API.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_DIR, HISTORICAL_MESSAGE_LIMIT
from logger import get_logger

logger = get_logger()

FACEBOOK_STORAGE_STATE: Path = BASE_DIR / "session" / "facebook_storage.json"

_STORY_SELECTORS: tuple[str, ...] = (
    '[data-ad-rendering-role="story_message"]',
    '[data-ad-preview="message"]',
    'div[data-ad-comet-preview="message"]',
    'div[dir="auto"]',
)


@dataclass(frozen=True)
class ScrapedPost:
    """A post scraped from a public Facebook page."""

    id: str
    message: str
    created_time: str | None = None


def page_url(page_id: str) -> str:
    """Build a Facebook page URL from an id or vanity name."""
    page_id = page_id.strip().strip("/")
    if page_id.startswith("http://") or page_id.startswith("https://"):
        return page_id
    return f"https://www.facebook.com/{page_id}"


def _stable_id(page_id: str, text: str) -> str:
    """Create a stable message id from page + post text."""
    digest: str = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return f"{page_id}:{digest}"


def _looks_like_rate_post(text: str) -> bool:
    """Heuristic filter for exchange-rate style posts."""
    lowered: str = text.lower()
    if "ကျပ်ပေး" in text or "ဘတ်ပေး" in text:
        return True
    if "buying" in lowered and "selling" in lowered:
        return True
    if re.search(r"\b\d{3,4}\b", text) and ("သိန်း" in text or "rate" in lowered):
        return True
    return len(text) >= 40


async def scrape_page_posts(
    page_id: str,
    *,
    limit: int = HISTORICAL_MESSAGE_LIMIT,
    storage_state: Path = FACEBOOK_STORAGE_STATE,
) -> list[ScrapedPost]:
    """Scrape recent posts from a Facebook page using a saved login session.

    Args:
        page_id: Page vanity name, numeric id, or full URL.
        limit: Max posts to return.
        storage_state: Playwright storage state from ``facebook_login.py``.

    Returns:
        Newest-first scraped posts.

    Raises:
        FileNotFoundError: When the browser session file is missing.
        RuntimeError: When Playwright cannot load posts.
    """
    if not storage_state.exists():
        raise FileNotFoundError(
            f"Missing Facebook session file: {storage_state}. "
            "Run: python facebook_login.py"
        )

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is required for public Facebook sync. "
            "Run: pip install playwright && playwright install chromium"
        ) from exc

    url: str = page_url(page_id)
    posts: list[ScrapedPost] = []
    seen: set[str] = set()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=str(storage_state))
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(3000)

        # Scroll to load more posts.
        for _ in range(min(8, max(1, limit // 5))):
            await page.mouse.wheel(0, 3500)
            await page.wait_for_timeout(1500)

        texts: list[str] = []
        for selector in _STORY_SELECTORS:
            nodes = await page.query_selector_all(selector)
            for node in nodes:
                try:
                    text = (await node.inner_text()).strip()
                except Exception:  # noqa: BLE001
                    continue
                if text and text not in texts:
                    texts.append(text)

        # Fallback: large text blocks from the feed.
        if len(texts) < 3:
            body_text: str = await page.inner_text("body")
            chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", body_text)]
            for chunk in chunks:
                if chunk and chunk not in texts:
                    texts.append(chunk)

        await browser.close()

    now_iso: str = datetime.now(timezone.utc).isoformat()
    for text in texts:
        normalized: str = re.sub(r"\s+", " ", text).strip()
        if not _looks_like_rate_post(normalized):
            continue
        message_id: str = _stable_id(page_id, normalized)
        if message_id in seen:
            continue
        seen.add(message_id)
        posts.append(
            ScrapedPost(id=message_id, message=normalized, created_time=now_iso)
        )
        if len(posts) >= limit:
            break

    if not posts:
        logger.warning(
            "No Facebook posts extracted from %s (login expired or UI changed)",
            page_id,
        )
    return posts


def scraped_to_graph_shape(post: ScrapedPost) -> dict[str, Any]:
    """Adapt a scraped post to the Graph-like dict used by FacebookService."""
    return {
        "id": post.id,
        "message": post.message,
        "created_time": post.created_time,
    }
