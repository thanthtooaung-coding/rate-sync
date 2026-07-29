# rate-sync

Monitors Telegram channels and optional Facebook pages for exchange-rate posts, parses rates, and writes them to Excel.

## Features

- Multi-source architecture: Telegram (Telethon) + Facebook (Graph API polling)
- Shared parser and Excel pipeline
- Workbook layout:
  1. **Avg Rate** — average of each feed’s latest rates (Telegram + Facebook)
  2. Telegram channel sheets
  3. Facebook page sheets
- Backfill recent posts on startup, then listen/poll live
- Skip duplicate message IDs per feed
- Auto-reconnect (Telegram) and resilient poll retries (Facebook)
- Console + `logs/app.log` logging

## Requirements

- Python 3.12+
- Neon PostgreSQL database
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)
- Optional: Facebook Page Access Token + Page ID(s) from [Meta for Developers](https://developers.facebook.com/)

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Put your Neon connection string in `.env`:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST/neondb?sslmode=require
```

3. Seed Telegram/Facebook settings into Neon (one-time):

```bash
python seed_settings.py --api-id YOUR_API_ID --api-hash YOUR_API_HASH --channels dimyanmarexchange
```

Facebook **without Page admin** (public scrape via your personal Facebook login):

```bash
pip install playwright
playwright install chromium
python facebook_login.py
python seed_settings.py --api-id YOUR_API_ID --api-hash YOUR_API_HASH --channels dimyanmarexchange --facebook-pages dimyanmar.org
```

Facebook **with Page admin** (official Graph API — optional token):

```bash
python seed_settings.py --api-id YOUR_API_ID --api-hash YOUR_API_HASH --channels dimyanmarexchange --facebook-token EAAB... --facebook-pages 1234567890
```

Multiple channels/pages: comma-separated in `--channels` / `--facebook-pages`.

Settings live in the `app_settings` table. Re-run `seed_settings.py` anytime to update them.

4. Run:

```bash
python app.py
```

On first run, Telethon asks for your phone number and login code (sent inside Telegram). The session is saved under `session/`.

Facebook modes:
- `facebook_page_ids` only → public scrape (requires `python facebook_login.py` once)
- `facebook_page_ids` + `facebook_access_token` → Graph API
- neither → Facebook disabled

Public scrape is unofficial and may break when Facebook changes their UI.

## Excel output

File: `data/exchange.xlsx`

### Sheet 1 — Avg Rate

| Date | Time | Avg Buy 5Lakh | Avg Buy 10Lakh | Avg Sell | Avg Sell Alt | Sources |
|------|------|---------------|----------------|----------|--------------|---------|

Updated once after historical download, then again on each live insert.

### Telegram sheets

Names like `dimyanmarexchange's Rates` (Excel 31-char limit).

| Date | Time | Buy 5Lakh | Buy 10Lakh | Sell | Sell Alt | Message ID | Raw Message |
|------|------|-----------|------------|------|----------|------------|-------------|

### Facebook sheets

Names like `FB SomePage's Rates`.

Same columns as Telegram sheets.

## Architecture

```text
app.py
  ├── services/telegram_service.py
  ├── services/facebook_service.py
  ├── services/rate_pipeline.py
  ├── excel_service.py
  ├── parser.py
  ├── models.py
  ├── db.py                  # Neon app_settings access
  ├── seed_settings.py       # one-time / update settings seeder
  └── config.py              # loads settings from database
```

## Facebook token tips (admin only)

1. Create a Meta app and add Pages products as needed.
2. Generate a **Page Access Token** with permission to read page posts.
3. Put token + page id(s) in Neon via `seed_settings.py`.

If you are **not** a Page admin, use `python facebook_login.py` instead (personal login session + public scrape).

Polling interval defaults to 300 seconds (5 minutes).

## Parsed message format

Example post:

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
| Sell Alt | second number when present |

## Project structure

```text
rate-sync/
├── app.py
├── config.py
├── db.py
├── seed_settings.py
├── models.py
├── parser.py
├── excel_service.py
├── logger.py
├── services/
│   ├── telegram_service.py
│   ├── facebook_service.py
│   └── rate_pipeline.py
├── requirements.txt
├── .env                 # DATABASE_URL only
├── data/
├── session/
└── logs/
```

## Notes

- You must already be able to view the Telegram channels with your account.
- Do not commit `.env` or `*.session` files.
- Stop with `Ctrl+C`.
