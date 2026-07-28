"""Facebook Graph API page-post polling service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from config import HISTORICAL_MESSAGE_LIMIT, Settings
from logger import get_logger
from models import SourceKind, SourcePost
from services.rate_pipeline import RatePipeline

logger = get_logger()

GRAPH_API_BASE: str = "https://graph.facebook.com/v21.0"


@dataclass
class FacebookService:
    """Poll Facebook page posts and forward them to the rate pipeline."""

    settings: Settings
    pipeline: RatePipeline
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        """Return True when Facebook credentials are configured."""
        return self.settings.facebook_enabled

    async def download_history(self) -> None:
        """Fetch recent posts for each configured page once at startup."""
        if not self.enabled:
            logger.info("Facebook sync disabled (token/pages not configured)")
            return

        logger.info(
            "Facebook sync enabled for pages: %s",
            ", ".join(self.settings.facebook_page_ids),
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            for page_id in self.settings.facebook_page_ids:
                logger.info(
                    "Downloading latest %s Facebook posts from %s",
                    HISTORICAL_MESSAGE_LIMIT,
                    page_id,
                )
                try:
                    posts = await self._fetch_posts(
                        client,
                        page_id,
                        limit=HISTORICAL_MESSAGE_LIMIT,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Facebook history fetch failed for %s: %s",
                        page_id,
                        exc,
                    )
                    continue

                for post in reversed(posts):
                    await self._emit_post(page_id, post, origin="history")

                logger.info("Facebook historical download complete for %s", page_id)

    async def start_polling(self) -> None:
        """Start the background poll loop (no-op when Facebook is disabled)."""
        if not self.enabled:
            return
        self._task = asyncio.create_task(self._poll_loop(), name="facebook-poller")
        logger.info(
            "Facebook poller started (interval=%ss)",
            self.settings.facebook_poll_interval_seconds,
        )

    async def _poll_loop(self) -> None:
        """Continuously poll pages for new posts."""
        interval: int = self.settings.facebook_poll_interval_seconds

        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass

            if self._shutdown_event.is_set():
                break

            async with httpx.AsyncClient(timeout=30.0) as client:
                for page_id in self.settings.facebook_page_ids:
                    try:
                        posts = await self._fetch_posts(
                            client,
                            page_id,
                            limit=HISTORICAL_MESSAGE_LIMIT,
                        )
                        for post in reversed(posts):
                            await self._emit_post(page_id, post, origin="live")
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "Facebook poll failed for %s: %s",
                            page_id,
                            exc,
                        )

    async def _fetch_posts(
        self,
        client: httpx.AsyncClient,
        page_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch recent posts for a page from the Graph API."""
        assert self.settings.facebook_access_token is not None
        response = await client.get(
            f"{GRAPH_API_BASE}/{page_id}/posts",
            params={
                "fields": "id,message,created_time",
                "limit": limit,
                "access_token": self.settings.facebook_access_token,
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        if "error" in payload:
            error = payload["error"]
            raise RuntimeError(f"Graph API error: {error.get('message', error)}")
        data = payload.get("data", [])
        return data if isinstance(data, list) else []

    async def _emit_post(
        self,
        page_id: str,
        post: dict[str, Any],
        *,
        origin: str,
    ) -> None:
        """Convert a Graph API post into a SourcePost and process it."""
        message_id: str = str(post.get("id") or "")
        text: str = str(post.get("message") or "")
        if not message_id:
            return

        created_raw: str | None = post.get("created_time")
        if created_raw:
            try:
                message_date = datetime.fromisoformat(
                    created_raw.replace("Z", "+00:00")
                )
                if message_date.tzinfo is not None:
                    message_date = message_date.astimezone().replace(tzinfo=None)
            except ValueError:
                message_date = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            message_date = datetime.now(timezone.utc).replace(tzinfo=None)

        await self.pipeline.handle_post(
            SourcePost(
                source=SourceKind.FACEBOOK,
                source_key=page_id,
                message_id=message_id,
                message_date=message_date,
                text=text,
            ),
            origin=origin,
        )

    async def stop(self) -> None:
        """Stop the poll loop and cancel the background task."""
        self._shutdown_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Facebook poller stopped")
