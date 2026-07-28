"""Shared domain models for rate sync sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from parser import ExchangeRate


class SourceKind(str, Enum):
    """Upstream platform that produced a rate post."""

    TELEGRAM = "telegram"
    FACEBOOK = "facebook"


@dataclass(frozen=True)
class SourcePost:
    """Normalized post from any rate source."""

    source: SourceKind
    source_key: str
    message_id: str
    message_date: datetime
    text: str


@dataclass(frozen=True)
class RateRecord:
    """A parsed exchange-rate row ready for Excel."""

    source: SourceKind
    source_key: str
    message_id: str
    message_date: datetime
    rates: ExchangeRate
    raw_message: str


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
