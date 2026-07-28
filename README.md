# rate-sync

Monitors Telegram exchange-rate channels with your personal Telegram account (Telethon), parses rates, and writes them to Excel.

## Features

- Login with Telegram Client API (not a bot)
- Listen to one or more public channels
- Backfill the latest 100 messages on startup, then listen live
- Parse Myanmar-format rate posts (and legacy English Buying/Selling/Cash)
- Excel workbook with:
  - **Avg Rate** (first sheet) — average of each channel’s latest rates
  - **`{channel}'s Exchange Rate`** — per-channel history
- Skip duplicate Telegram message IDs per channel
- Auto-reconnect and graceful Ctrl+C shutdown
- Console + `logs/app.log` logging

## Requirements

- Python 3.12+
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create `.env` in the project root:

```env
API_ID=your_api_id
API_HASH=your_api_hash
CHANNEL_USERNAME=
```

Multiple channels (comma-separated):

```env
CHANNEL_USERNAME=firstchannel,anotherchannel
```

3. Run:

```bash
python app.py
```

On first run, Telethon asks for your phone number and login code (sent inside Telegram). The session is saved under `session/` so you are not asked again.

## Excel output

File: `data/exchange.xlsx`

### Sheet 1 — Avg Rate

| Date | Time | Avg Buy 5Lakh | Avg Buy 10Lakh | Avg Sell | Avg Sell Alt | Channels |
|------|------|---------------|----------------|----------|--------------|----------|

Updated once after historical download, then again on each live rate insert.

### Sheet 2+ — per channel

Sheet name examples:

- `shortname's Exchange Rate`

| Date | Time | Buy 5Lakh | Buy 10Lakh | Sell | Sell Alt | Telegram Message ID | Raw Message |
|------|------|-----------|------------|------|----------|---------------------|-------------|

## Parsed message format

Example channel post:

```text
📌 ကျပ်ပေး ဘတ်ယူ
      ✅ ၅ သိန်းအထက် - 752
      ✅ ၁၀ သိန်း အထက် - 754

📌 ဘတ်ပေး ကျပ်ယူ - 775 / 773
```

| Field | Source |
|-------|--------|
| Buy 5Lakh | `၅ သိန်းအထက်` |
| Buy 10Lakh | `၁၀ သိန်း အထက်` |
| Sell | first number in `ဘတ်ပေး ကျပ်ယူ` |
| Sell Alt | second number when present (`775 / 773`) |

## Project structure

```text
rate-sync/
├── app.py              # Telethon listener + orchestration
├── config.py           # .env settings
├── parser.py           # Rate parsing
├── excel_service.py    # Excel read/write
├── logger.py           # Console + file logging
├── requirements.txt
├── .env
├── data/
│   └── exchange.xlsx
├── session/
│   └── telegram.session
└── logs/
    └── app.log
```

## Notes

- You must already be able to view the target channels with your Telegram account.
- Do not commit `.env` or `*.session` files (they are gitignored).
- Stop the app with `Ctrl+C`.
