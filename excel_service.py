"""Excel persistence for exchange-rate records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from config import EXCEL_PATH, ensure_directories
from parser import ExchangeRate

AVG_SHEET_NAME: str = "Avg Rate"

AVG_HEADERS: tuple[str, ...] = (
    "Date",
    "Time",
    "Avg Buy 5Lakh",
    "Avg Buy 10Lakh",
    "Avg Sell",
    "Avg Sell Alt",
    "Channels",
)

CHANNEL_HEADERS: tuple[str, ...] = (
    "Date",
    "Time",
    "Buy 5Lakh",
    "Buy 10Lakh",
    "Sell",
    "Sell Alt",
    "Telegram Message ID",
    "Raw Message",
)

MESSAGE_ID_COLUMN: int = 7
_INVALID_SHEET_CHARS: re.Pattern[str] = re.compile(r"[\\/*?:\[\]]")


def sheet_name_for_channel(channel: str) -> str:
    """Build an Excel sheet title for a channel.

    Prefers ``{channel}'s Exchange Rate``. Falls back to shorter forms when
    the Excel 31-character sheet-name limit would be exceeded.

    Args:
        channel: Telegram channel username.

    Returns:
        A safe sheet title for the channel.
    """
    safe: str = _INVALID_SHEET_CHARS.sub("_", channel.strip().lstrip("@"))
    for suffix in ("'s Exchange Rate", "'s Rates", ""):
        title: str = f"{safe}{suffix}" if suffix else safe
        if len(title) <= 31:
            return title
    return safe[:31]


@dataclass(frozen=True)
class RateRecord:
    """A single exchange-rate row ready for Excel."""

    channel: str
    message_id: int
    message_date: datetime
    rates: ExchangeRate
    raw_message: str


@dataclass(frozen=True)
class AverageRate:
    """Averaged rates across channels that currently have data."""

    buy_5_lakh: float
    buy_10_lakh: float
    sell: float
    sell_alt: float | None
    channels_used: int


@dataclass
class ExcelService:
    """Persist rates into an Avg Rate sheet plus per-channel sheets."""

    channels: list[str]
    path: Path = EXCEL_PATH
    _known_ids: dict[str, set[int]] = field(default_factory=dict, init=False)
    _latest_rates: dict[str, ExchangeRate] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        """Ensure workbook/sheets exist and load known message IDs."""
        if not self.channels:
            raise ValueError("At least one channel is required")
        ensure_directories()
        self._ensure_workbook()
        self._known_ids = self._load_existing_message_ids()
        self._latest_rates = self._load_latest_rates()

    def _create_workbook(self) -> None:
        """Create Avg Rate first, then one sheet per channel."""
        workbook: Workbook = Workbook()
        default_sheet: Worksheet = workbook.active
        workbook.remove(default_sheet)

        avg_sheet: Worksheet = workbook.create_sheet(title=AVG_SHEET_NAME, index=0)
        avg_sheet.append(list(AVG_HEADERS))

        for channel in self.channels:
            sheet: Worksheet = workbook.create_sheet(title=sheet_name_for_channel(channel))
            sheet.append(list(CHANNEL_HEADERS))

        workbook.save(self.path)

    def _row_headers(self, sheet: Worksheet) -> tuple[object | None, ...]:
        """Return the header tuple for a sheet."""
        return tuple(
            cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))
        )

    def _workbook_schema_ok(self, workbook: Workbook) -> bool:
        """Validate Avg Rate + at least one channel sheet schema."""
        if AVG_SHEET_NAME not in workbook.sheetnames:
            return False
        avg_headers: tuple[object | None, ...] = self._row_headers(
            workbook[AVG_SHEET_NAME]
        )
        if avg_headers[: len(AVG_HEADERS)] != AVG_HEADERS:
            return False

        for channel in self.channels:
            title: str = sheet_name_for_channel(channel)
            if title not in workbook.sheetnames:
                continue
            channel_headers: tuple[object | None, ...] = self._row_headers(workbook[title])
            if channel_headers[: len(CHANNEL_HEADERS)] != CHANNEL_HEADERS:
                return False
        return True

    def _ensure_avg_first(self, workbook: Workbook) -> None:
        """Move Avg Rate sheet to index 0."""
        if AVG_SHEET_NAME in workbook.sheetnames:
            workbook.move_sheet(AVG_SHEET_NAME, offset=-workbook.sheetnames.index(AVG_SHEET_NAME))

    def _ensure_workbook(self) -> None:
        """Create the workbook and ensure Avg Rate + channel sheets exist."""
        if not self.path.exists():
            self._create_workbook()
            return

        workbook = load_workbook(self.path)
        if not self._workbook_schema_ok(workbook):
            workbook.close()
            backup: Path = self.path.with_suffix(".bak.xlsx")
            if backup.exists():
                backup.unlink()
            self.path.replace(backup)
            self._create_workbook()
            return

        if AVG_SHEET_NAME not in workbook.sheetnames:
            avg_sheet: Worksheet = workbook.create_sheet(title=AVG_SHEET_NAME, index=0)
            avg_sheet.append(list(AVG_HEADERS))
        else:
            self._ensure_avg_first(workbook)

        for channel in self.channels:
            title: str = sheet_name_for_channel(channel)
            if title not in workbook.sheetnames:
                sheet: Worksheet = workbook.create_sheet(title=title)
                sheet.append(list(CHANNEL_HEADERS))

        workbook.save(self.path)
        workbook.close()

    def _channel_key(self, channel: str) -> str:
        """Normalize channel usernames for lookups."""
        return channel.strip().lstrip("@").lower()

    def _load_existing_message_ids(self) -> dict[str, set[int]]:
        """Load Telegram message IDs already stored per channel sheet."""
        workbook = load_workbook(self.path, read_only=True, data_only=True)
        known: dict[str, set[int]] = {
            self._channel_key(channel): set() for channel in self.channels
        }

        title_to_channel: dict[str, str] = {
            sheet_name_for_channel(channel): self._channel_key(channel)
            for channel in self.channels
        }

        for sheet in workbook.worksheets:
            channel_key: str | None = title_to_channel.get(sheet.title)
            if channel_key is None:
                continue
            for row in sheet.iter_rows(
                min_row=2,
                min_col=MESSAGE_ID_COLUMN,
                max_col=MESSAGE_ID_COLUMN,
                values_only=True,
            ):
                value = row[0]
                if value is None:
                    continue
                try:
                    known[channel_key].add(int(value))
                except (TypeError, ValueError):
                    continue

        workbook.close()
        return known

    def _load_latest_rates(self) -> dict[str, ExchangeRate]:
        """Load the newest rate row from each channel sheet."""
        workbook = load_workbook(self.path, read_only=True, data_only=True)
        latest: dict[str, ExchangeRate] = {}

        for channel in self.channels:
            title: str = sheet_name_for_channel(channel)
            if title not in workbook.sheetnames:
                continue
            sheet: Worksheet = workbook[title]
            last_rate: ExchangeRate | None = None
            for row in sheet.iter_rows(min_row=2, values_only=True):
                try:
                    buy_5 = int(row[2])  # type: ignore[arg-type]
                    buy_10 = int(row[3])  # type: ignore[arg-type]
                    sell = int(row[4])  # type: ignore[arg-type]
                except (TypeError, ValueError, IndexError):
                    continue
                sell_alt: int | None
                try:
                    sell_alt = int(row[5]) if row[5] not in (None, "") else None
                except (TypeError, ValueError):
                    sell_alt = None
                last_rate = ExchangeRate(
                    buy_5_lakh=buy_5,
                    buy_10_lakh=buy_10,
                    sell=sell,
                    sell_alt=sell_alt,
                )
            if last_rate is not None:
                latest[self._channel_key(channel)] = last_rate

        workbook.close()
        return latest

    def has_message(self, channel: str, message_id: int) -> bool:
        """Check whether a Telegram message ID is already stored for a channel."""
        return message_id in self._known_ids.get(self._channel_key(channel), set())

    def compute_average(self) -> AverageRate | None:
        """Average the latest rates across channels that have data."""
        rates: list[ExchangeRate] = list(self._latest_rates.values())
        if not rates:
            return None

        count: int = len(rates)
        sell_alts: list[int] = [
            rate.sell_alt for rate in rates if rate.sell_alt is not None
        ]
        return AverageRate(
            buy_5_lakh=round(sum(rate.buy_5_lakh for rate in rates) / count, 2),
            buy_10_lakh=round(sum(rate.buy_10_lakh for rate in rates) / count, 2),
            sell=round(sum(rate.sell for rate in rates) / count, 2),
            sell_alt=(
                round(sum(sell_alts) / len(sell_alts), 2) if sell_alts else None
            ),
            channels_used=count,
        )

    def write_average_snapshot(self, as_of: datetime | None = None) -> bool:
        """Append current cross-channel average to the Avg Rate sheet.

        Args:
            as_of: Timestamp for the snapshot. Defaults to now.

        Returns:
            True if a row was written.
        """
        average: AverageRate | None = self.compute_average()
        if average is None:
            return False

        stamp: datetime = as_of or datetime.now()
        workbook = load_workbook(self.path)
        if AVG_SHEET_NAME not in workbook.sheetnames:
            avg_sheet: Worksheet = workbook.create_sheet(title=AVG_SHEET_NAME, index=0)
            avg_sheet.append(list(AVG_HEADERS))
        else:
            avg_sheet = workbook[AVG_SHEET_NAME]
            self._ensure_avg_first(workbook)

        avg_sheet.append(
            [
                stamp.strftime("%Y-%m-%d"),
                stamp.strftime("%H:%M:%S"),
                average.buy_5_lakh,
                average.buy_10_lakh,
                average.sell,
                average.sell_alt if average.sell_alt is not None else "",
                average.channels_used,
            ]
        )
        workbook.save(self.path)
        workbook.close()
        return True

    def append_record(self, record: RateRecord, *, update_average: bool = False) -> bool:
        """Append a rate record to the channel sheet if it is not a duplicate.

        Args:
            record: Parsed rate record to store.
            update_average: When True, also append an Avg Rate snapshot.

        Returns:
            True if a channel row was inserted, False if skipped as duplicate.
        """
        channel_key: str = self._channel_key(record.channel)
        if self.has_message(channel_key, record.message_id):
            return False

        workbook = load_workbook(self.path)
        title: str = sheet_name_for_channel(record.channel)
        if title not in workbook.sheetnames:
            sheet: Worksheet = workbook.create_sheet(title=title)
            sheet.append(list(CHANNEL_HEADERS))
        else:
            sheet = workbook[title]

        sheet.append(
            [
                record.message_date.strftime("%Y-%m-%d"),
                record.message_date.strftime("%H:%M:%S"),
                record.rates.buy_5_lakh,
                record.rates.buy_10_lakh,
                record.rates.sell,
                record.rates.sell_alt if record.rates.sell_alt is not None else "",
                record.message_id,
                record.raw_message,
            ]
        )
        workbook.save(self.path)
        workbook.close()

        self._known_ids.setdefault(channel_key, set()).add(record.message_id)
        self._latest_rates[channel_key] = record.rates

        if update_average:
            self.write_average_snapshot(record.message_date)
        return True

    def append_many(self, records: Iterable[RateRecord]) -> tuple[int, int]:
        """Append multiple records, skipping duplicates."""
        inserted: int = 0
        skipped: int = 0

        for record in records:
            if self.append_record(record):
                inserted += 1
            else:
                skipped += 1

        return inserted, skipped
