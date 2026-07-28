"""Telegram channel listener service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.errors import RPCError
from telethon.tl.custom.message import Message

from config import HISTORICAL_MESSAGE_LIMIT, SESSION_PATH, Settings
from logger import get_logger
from models import SourceKind, SourcePost
from services.rate_pipeline import RatePipeline

logger = get_logger()


@dataclass
class TelegramService:
    """Listen to Telegram channels and forward posts to the rate pipeline."""

    settings: Settings
    pipeline: RatePipeline
    client: TelegramClient | None = None
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)

    async def client_start_and_history(self) -> None:
        """Connect to Telegram and backfill recent channel messages."""
        self.client = TelegramClient(
            str(SESSION_PATH),
            self.settings.api_id,
            self.settings.api_hash,
        )
        await self.client.start()
        logger.info("Telegram connected")
        await self.download_history()

    async def download_history(self) -> None:
        """Download recent messages from every configured Telegram channel."""
        assert self.client is not None

        for channel in self.settings.channel_usernames:
            logger.info(
                "Downloading latest %s messages from @%s",
                HISTORICAL_MESSAGE_LIMIT,
                channel,
            )
            messages: list[Message] = []
            async for message in self.client.iter_messages(
                channel,
                limit=HISTORICAL_MESSAGE_LIMIT,
            ):
                messages.append(message)

            for message in reversed(messages):
                await self._emit_message(message, channel=channel, origin="history")

            logger.info("Historical download complete for @%s", channel)

    async def run_live(self) -> None:
        """Register live handlers and run until disconnect/shutdown."""
        self._register_handlers()
        await self._run_until_disconnected()

    def _register_handlers(self) -> None:
        """Register live new-message handlers for configured channels."""
        assert self.client is not None
        channels: list[str] = list(self.settings.channel_usernames)

        @self.client.on(events.NewMessage(chats=channels))
        async def on_new_message(event: events.NewMessage.Event) -> None:
            message: Message = event.message
            channel: str = await self._resolve_channel(event)
            await self._emit_message(message, channel=channel, origin="live")

    async def _resolve_channel(self, event: events.NewMessage.Event) -> str:
        """Resolve the channel username for a live event."""
        assert self.client is not None
        chat = await event.get_chat()
        username: str | None = getattr(chat, "username", None)
        if username:
            return username

        chat_id = getattr(chat, "id", None)
        for channel in self.settings.channel_usernames:
            try:
                entity = await self.client.get_entity(channel)
                if getattr(entity, "id", None) == chat_id:
                    return channel
            except Exception:  # noqa: BLE001
                continue
        return str(chat_id or "unknown")

    async def _emit_message(
        self,
        message: Message,
        *,
        channel: str,
        origin: str,
    ) -> None:
        """Convert a Telethon message into a SourcePost and process it."""
        text: str = message.message or ""
        message_date: datetime = message.date or datetime.now(timezone.utc)
        if message_date.tzinfo is not None:
            message_date = message_date.astimezone().replace(tzinfo=None)

        await self.pipeline.handle_post(
            SourcePost(
                source=SourceKind.TELEGRAM,
                source_key=channel,
                message_id=str(message.id),
                message_date=message_date,
                text=text,
            ),
            origin=origin,
        )

    async def _run_until_disconnected(self) -> None:
        """Keep the client running with automatic reconnect support."""
        assert self.client is not None

        while not self._shutdown_event.is_set():
            try:
                await self.client.run_until_disconnected()
                if self._shutdown_event.is_set():
                    break
                logger.warning("Telegram disconnected; reconnecting...")
                await self.client.connect()
                logger.info("Telegram connected")
            except asyncio.CancelledError:
                break
            except (OSError, RPCError) as exc:
                logger.error("Connection error: %s; retrying in 5s", exc)
                await asyncio.sleep(5)
                try:
                    await self.client.connect()
                    logger.info("Telegram connected")
                except Exception as reconnect_exc:  # noqa: BLE001
                    logger.error("Reconnect failed: %s", reconnect_exc)
                    await asyncio.sleep(5)

    async def stop(self) -> None:
        """Disconnect Telethon cleanly."""
        self._shutdown_event.set()
        if self.client is not None and self.client.is_connected():
            await self.client.disconnect()
            logger.info("Telegram disconnected cleanly")
