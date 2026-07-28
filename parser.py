"""Independent parser for Telegram exchange-rate messages."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExchangeRate:
    """Parsed exchange rate values from a channel post.

    Attributes:
        buy_5_lakh: MMK→THB rate for ၅ သိန်းအထက်.
        buy_10_lakh: MMK→THB rate for ၁၀ သိန်းအထက်.
        sell: Primary THB→MMK rate from ဘတ်ပေး ကျပ်ယူ.
        sell_alt: Optional second THB→MMK tier rate.
    """

    buy_5_lakh: int
    buy_10_lakh: int
    sell: int
    sell_alt: int | None = None


# Myanmar channel format (dimyanmarexchange)
_BUY_5_PATTERN: re.Pattern[str] = re.compile(
    r"၅\s*သိန်း\s*အထက်\s*[-–—:]\s*(\d+(?:[.,]\d+)?)",
)
_BUY_10_PATTERN: re.Pattern[str] = re.compile(
    r"၁၀\s*သိန်း\s*အထက်\s*[-–—:]\s*(\d+(?:[.,]\d+)?)",
)
_SELL_PATTERN: re.Pattern[str] = re.compile(
    r"ဘတ်ပေး\s*ကျပ်ယူ\s*[-–—:]\s*(\d+(?:[.,]\d+)?)"
    r"(?:\s*/\s*(\d+(?:[.,]\d+)?))?",
)

# Legacy English format from the original plan
_EN_BUY_PATTERN: re.Pattern[str] = re.compile(
    r"Buying\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_EN_SELL_PATTERN: re.Pattern[str] = re.compile(
    r"Selling\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_EN_CASH_PATTERN: re.Pattern[str] = re.compile(
    r"Cash\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def _to_int(raw_value: str) -> int:
    """Convert a numeric string to an integer rate.

    Args:
        raw_value: Captured numeric text (may include decimals/commas).

    Returns:
        Integer rate value.
    """
    normalized: str = raw_value.replace(",", ".")
    return int(float(normalized))


def _parse_myanmar(text: str) -> ExchangeRate | None:
    """Parse rates from Myanmar-language channel posts."""
    buy_5: re.Match[str] | None = _BUY_5_PATTERN.search(text)
    buy_10: re.Match[str] | None = _BUY_10_PATTERN.search(text)
    sell_match: re.Match[str] | None = _SELL_PATTERN.search(text)

    if not (buy_5 and buy_10 and sell_match):
        return None

    try:
        sell_alt_raw: str | None = sell_match.group(2)
        return ExchangeRate(
            buy_5_lakh=_to_int(buy_5.group(1)),
            buy_10_lakh=_to_int(buy_10.group(1)),
            sell=_to_int(sell_match.group(1)),
            sell_alt=_to_int(sell_alt_raw) if sell_alt_raw else None,
        )
    except (TypeError, ValueError):
        return None


def _parse_english(text: str) -> ExchangeRate | None:
    """Parse rates from legacy English Buying/Selling/Cash messages."""
    buy_match: re.Match[str] | None = _EN_BUY_PATTERN.search(text)
    sell_match: re.Match[str] | None = _EN_SELL_PATTERN.search(text)
    cash_match: re.Match[str] | None = _EN_CASH_PATTERN.search(text)

    if not (buy_match and sell_match and cash_match):
        return None

    try:
        return ExchangeRate(
            buy_5_lakh=_to_int(buy_match.group(1)),
            buy_10_lakh=_to_int(cash_match.group(1)),
            sell=_to_int(sell_match.group(1)),
            sell_alt=None,
        )
    except (TypeError, ValueError):
        return None


def parse_message(text: str | None) -> ExchangeRate | None:
    """Parse buy/sell rates from a message body.

    Supports the live Myanmar channel format and the legacy English format.

    Args:
        text: Raw Telegram message text.

    Returns:
        ExchangeRate on success, or None if parsing fails.
    """
    if not text:
        return None

    return _parse_myanmar(text) or _parse_english(text)
