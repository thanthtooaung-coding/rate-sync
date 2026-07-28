"""Shared parse-and-persist pipeline for all rate sources."""

from __future__ import annotations

from dataclasses import dataclass

from excel_service import ExcelService, sheet_name_for_source
from logger import get_logger
from models import RateRecord, SourcePost, Stats
from parser import ExchangeRate, parse_message

logger = get_logger()


@dataclass
class RatePipeline:
    """Parse source posts and write accepted rates into Excel."""

    excel: ExcelService
    stats: Stats

    async def handle_post(self, post: SourcePost, *, origin: str) -> None:
        """Ingest one normalized post.

        Args:
            post: Normalized source post.
            origin: ``history`` or ``live``.
        """
        self.stats.messages_processed += 1

        print(
            f"\n[{origin}] Source: {post.source.value} / {post.source_key}\n"
            f"Date: {post.message_date}\n"
            f"Message ID: {post.message_id}\n"
            f"Full Message:\n{post.text}\n"
        )
        logger.info(
            "New message received (source=%s, key=%s, id=%s, origin=%s)",
            post.source.value,
            post.source_key,
            post.message_id,
            origin,
        )

        if self.excel.has_message(post.source, post.source_key, post.message_id):
            self.stats.rows_skipped += 1
            logger.info(
                "Skipping duplicate message source=%s key=%s id=%s",
                post.source.value,
                post.source_key,
                post.message_id,
            )
            return

        rates: ExchangeRate | None = parse_message(post.text)
        if rates is None:
            self.stats.rows_skipped += 1
            logger.info(
                "Parsed values: None (source=%s, key=%s, id=%s)",
                post.source.value,
                post.source_key,
                post.message_id,
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
                source=post.source,
                source_key=post.source_key,
                message_id=post.message_id,
                message_date=post.message_date,
                rates=rates,
                raw_message=post.text,
            ),
            update_average=(origin == "live"),
        )

        if inserted:
            self.stats.rows_inserted += 1
            logger.info(
                "Excel updated (source=%s, key=%s, id=%s, sheet=%s)",
                post.source.value,
                post.source_key,
                post.message_id,
                sheet_name_for_source(post.source, post.source_key),
            )
            if origin == "live":
                logger.info("Avg Rate sheet updated")
        else:
            self.stats.rows_skipped += 1
            logger.info(
                "Skipping duplicate message source=%s key=%s id=%s",
                post.source.value,
                post.source_key,
                post.message_id,
            )
