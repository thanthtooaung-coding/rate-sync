"""Multi-source rate sync orchestrator (Telegram + Facebook)."""

from __future__ import annotations

import asyncio
import signal
import sys
from dataclasses import dataclass, field

from config import Settings, ensure_directories, load_settings
from excel_service import ExcelService, sheet_name_for_source
from logger import setup_logger
from models import SourceKind, Stats
from services.facebook_service import FacebookService
from services.rate_pipeline import RatePipeline
from services.telegram_service import TelegramService

logger = setup_logger()


@dataclass
class RateSyncApp:
    """Start Excel, Telegram, and optional Facebook sync services."""

    settings: Settings
    stats: Stats = field(default_factory=Stats)
    excel: ExcelService = field(init=False)
    pipeline: RatePipeline = field(init=False)
    telegram: TelegramService = field(init=False)
    facebook: FacebookService = field(init=False)
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        """Wire shared Excel + pipeline into source services."""
        self.excel = ExcelService(
            telegram_channels=list(self.settings.channel_usernames),
            facebook_pages=list(self.settings.facebook_page_ids),
        )
        self.pipeline = RatePipeline(excel=self.excel, stats=self.stats)
        self.telegram = TelegramService(settings=self.settings, pipeline=self.pipeline)
        self.facebook = FacebookService(settings=self.settings, pipeline=self.pipeline)

    def _print_workbook_plan(self) -> None:
        """Print configured workbook sheet layout."""
        print("Workbook sheets:")
        print("  1. Avg Rate  (average of latest rates across Telegram + Facebook)")
        print("Telegram sheets:")
        for channel in self.settings.channel_usernames:
            title: str = sheet_name_for_source(SourceKind.TELEGRAM, channel)
            print(f"  @{channel} -> '{title}'")
            logger.info("Watching Telegram @%s (sheet=%s)", channel, title)

        if self.settings.facebook_enabled:
            print("Facebook sheets:")
            for page_id in self.settings.facebook_page_ids:
                title = sheet_name_for_source(SourceKind.FACEBOOK, page_id)
                print(f"  {page_id} -> '{title}'")
                logger.info("Watching Facebook page %s (sheet=%s)", page_id, title)
        else:
            print(
                "Facebook sheets: (disabled — set FACEBOOK_ACCESS_TOKEN "
                "+ FACEBOOK_PAGE_IDS)"
            )

    async def start(self) -> None:
        """Run historical backfill for all sources, then live listeners."""
        ensure_directories()
        logger.info("Application started")
        self._print_workbook_plan()

        await self.facebook.download_history()
        await self.telegram.client_start_and_history()

        if self.excel.write_average_snapshot():
            logger.info("Avg Rate sheet updated after historical download")
        self.stats.print_summary()

        await self.facebook.start_polling()
        try:
            await self.telegram.run_live()
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Stop all sources and print final statistics."""
        if self._shutdown_event.is_set():
            return

        self._shutdown_event.set()
        await self.facebook.stop()
        await self.telegram.stop()
        self.stats.print_summary()
        logger.info("Application stopped")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, app: RateSyncApp) -> None:
    """Register Ctrl+C handlers for graceful shutdown when supported."""

    def _request_shutdown() -> None:
        logger.info("Shutdown requested")
        loop.create_task(app.shutdown())

    if sys.platform == "win32":
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
