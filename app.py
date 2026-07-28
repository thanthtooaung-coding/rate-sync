"""Telegram channel listener that syncs exchange rates into Excel."""

from __future__ import annotations

import asyncio
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.errors import RPCError
from telethon.tl.custom.message import Message

from config import (
    HISTORICAL_MESSAGE_LIMIT,
    SESSION_PATH,
    Settings,
    ensure_directories,
    load_settings,
)
from excel_service import ExcelService, RateRecord, sheet_name_for_channel
from logger import setup_logger
from parser import ExchangeRate, parse_message

logger = setup_logger()


@dataclass
class Stats:
    """Runtime processing statistics."""

    messages_processed: int = 0
    rows_inserted: int = 0
    rows_skipped: int = 0

    def print_summary(self) -> None:
        """Print a compact statistics summary to the console."""
        print(
            "\n--- Statistics ---\n"
            f"Messages processed: {self.messages_processed}\n"
            f"Rows inserted: {self.rows_inserted}\n"
            f"Rows skipped: {self.rows_skipped}\n"
            "------------------\n"
        )


@dataclass
class RateSyncApp:
    """Orchestrates Telegram listening and Excel persistence."""

    settings: Settings
    stats: Stats = field(default_factory=Stats)
    excel: ExcelService = field(init=False)
    client: TelegramClient | None = None
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        """Create the Excel service for configured channels."""
        self.excel = ExcelService(channels=list(self.settings.channel_usernames))

    async def start(self) -> None:
        """Connect to Telegram, backfill history, then listen live."""
        ensure_directories()
        logger.info("Application started")

        self.client = TelegramClient(
            str(SESSION_PATH),
            self.settings.api_id,
            self.settings.api_hash,
        )

        await self.client.start()
        logger.info("Telegram connected")

        channels: tuple[str, ...] = self.settings.channel_usernames
        print("Workbook sheets:")
        print("  1. Avg Rate  (average of latest rates across channels)")
        print("Channel sheets:")
        for channel in channels:
            sheet: str = sheet_name_for_channel(channel)
            print(f"  @{channel} -> '{sheet}'")
            logger.info("Watching channel @%s (sheet=%s)", channel, sheet)

        await self._download_history()
        self._register_handlers()

        try:
            await self._run_until_disconnected()
        finally:
            await self.shutdown()

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

    def _register_handlers(self) -> None:
        """Register the live new-message handler for all configured channels."""
        assert self.client is not None
        channels: list[str] = list(self.settings.channel_usernames)

        @self.client.on(events.NewMessage(chats=channels))
        async def on_new_message(event: events.NewMessage.Event) -> None:
            message: Message = event.message
            channel: str = await self._resolve_channel(event)
            await self._handle_message(message, channel=channel, source="live")

    async def _resolve_channel(self, event: events.NewMessage.Event) -> str:
        """Resolve the channel username for a live event."""
        chat = await event.get_chat()
        username: str | None = getattr(chat, "username", None)
        if username:
            return username

        # Fallback: match against configured channels by id if needed.
        chat_id = getattr(chat, "id", None)
        for channel in self.settings.channel_usernames:
            try:
                entity = await self.client.get_entity(channel)  # type: ignore[union-attr]
                if getattr(entity, "id", None) == chat_id:
                    return channel
            except Exception:  # noqa: BLE001
                continue
        return str(chat_id or "unknown")

    async def _download_history(self) -> None:
        """Download recent messages from every configured channel."""
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
                await self._handle_message(
                    message,
                    channel=channel,
                    source="history",
                )

            logger.info("Historical download complete for @%s", channel)

        if self.excel.write_average_snapshot():
            logger.info("Avg Rate sheet updated after historical download")
        self.stats.print_summary()

    async def _handle_message(
        self,
        message: Message,
        channel: str,
        source: str,
    ) -> None:
        """Parse and persist a single Telegram message.

        Args:
            message: Incoming Telegram message.
            channel: Source channel username.
            source: Origin label (`history` or `live`).
        """
        self.stats.messages_processed += 1

        text: str = message.message or ""
        message_id: int = message.id
        message_date: datetime = message.date or datetime.now(timezone.utc)
        if message_date.tzinfo is not None:
            message_date = message_date.astimezone().replace(tzinfo=None)

        print(
            f"\n[{source}] Channel: @{channel}\n"
            f"Date: {message_date}\n"
            f"Message ID: {message_id}\n"
            f"Full Message:\n{text}\n"
        )
        logger.info(
            "New message received (channel=@%s, id=%s, source=%s)",
            channel,
            message_id,
            source,
        )

        if self.excel.has_message(channel, message_id):
            self.stats.rows_skipped += 1
            logger.info(
                "Skipping duplicate message channel=@%s id=%s",
                channel,
                message_id,
            )
            return

        rates: ExchangeRate | None = parse_message(text)
        if rates is None:
            self.stats.rows_skipped += 1
            logger.info(
                "Parsed values: None (channel=@%s, message id=%s)",
                channel,
                message_id,
            )
            return

        logger.info(
            "Parsed values: buy_5=%s buy_10=%s sell=%s sell_alt=%s",
            rates.buy_5_lakh,
            rates.buy_10_lakh,
            rates.sell,
            rates.sell_alt,
        )

        inserted: bool = self.excel.append_record(
            RateRecord(
                channel=channel,
                message_id=message_id,
                message_date=message_date,
                rates=rates,
                raw_message=text,
            ),
            update_average=(source == "live"),
        )

        if inserted:
            self.stats.rows_inserted += 1
            logger.info(
                "Excel updated (channel=@%s, message id=%s, sheet=%s)",
                channel,
                message_id,
                sheet_name_for_channel(channel),
            )
            if source == "live":
                logger.info("Avg Rate sheet updated")
        else:
            self.stats.rows_skipped += 1
            logger.info(
                "Skipping duplicate message channel=@%s id=%s",
                channel,
                message_id,
            )

    async def shutdown(self) -> None:
        """Disconnect Telethon cleanly and print final statistics."""
        self._shutdown_event.set()
        if self.client is not None and self.client.is_connected():
            await self.client.disconnect()
            logger.info("Telegram disconnected cleanly")
        self.stats.print_summary()
        logger.info("Application stopped")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, app: RateSyncApp) -> None:
    """Register Ctrl+C handlers for graceful shutdown when supported."""

    def _request_shutdown() -> None:
        logger.info("Shutdown requested")
        app._shutdown_event.set()
        if app.client is not None:
            loop.create_task(app.client.disconnect())

    if sys.platform == "win32":
        # ProactorEventLoop on Windows does not support add_signal_handler.
        signal.signal(signal.SIGINT, lambda *_: _request_shutdown())
        signal.signal(signal.SIGTERM, lambda *_: _request_shutdown())
        return

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _request_shutdown())


async def main() -> None:
    """Application entry point."""
    try:
        settings: Settings = load_settings()
    except ValueError as exc:
        logger.error("%s", exc)
        print(f"Configuration error: {exc}")
        sys.exit(1)

    app: RateSyncApp = RateSyncApp(settings=settings)
    loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
    _install_signal_handlers(loop, app)

    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        await app.shutdown()
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal error: %s", exc, exc_info=True)
        await app.shutdown()
        raise


if __name__ == "__main__":
    asyncio.run(main())
