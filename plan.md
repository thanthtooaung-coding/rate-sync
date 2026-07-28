You are a senior Python software engineer.

Build a production-ready Python application that automatically monitors a Telegram channel and updates an Excel file with exchange rates.

## Goal

The application logs into Telegram using MY Telegram account (NOT a bot), joins an existing public channel that I already joined, listens for new messages, extracts exchange rate information, and stores the data into an Excel spreadsheet.

Use the Telegram Client API (Telethon), not Telegram Bot API.

Example channel:

dimyanmarexchange

The application must run continuously until stopped.

--------------------------------------------------
Tech Stack
--------------------------------------------------

- Python 3.12+
- Telethon
- openpyxl
- python-dotenv
- asyncio
- logging
- regex

--------------------------------------------------
Project Structure
--------------------------------------------------

telegram-exchange/
│
├── app.py
├── config.py
├── parser.py
├── excel_service.py
├── logger.py
├── requirements.txt
├── .env
├── data/
│   └── exchange.xlsx
├── session/
│   └── telegram.session
└── logs/
    └── app.log

--------------------------------------------------
Environment Variables
--------------------------------------------------

Store secrets inside .env

API_ID=
API_HASH=
CHANNEL_USERNAME=dimyanmarexchange

--------------------------------------------------
Requirements
--------------------------------------------------

1.
Login using Telethon.

On first run ask for phone number and login code.

Save session.

Never ask again after session exists.

2.

Listen ONLY to

CHANNEL_USERNAME

3.

Whenever a new message arrives

Print

Date
Message ID
Full Message

4.

Parse exchange rates.

Example message:

Buying
753

Selling
755

Cash
775

Extract

buy_rate
sell_rate
cash_rate

Use regular expressions.

The parser should return

{
    "buy":753,
    "sell":755,
    "cash":775
}

If parsing fails

Return None

Do NOT crash.

5.

Create Excel automatically if it doesn't exist.

Columns

Date
Time
Buy
Sell
Cash
Raw Message

Append one row per message.

6.

Prevent duplicates.

If the same Telegram message ID already exists

Skip it.

7.

Create logs.

logs/app.log

Log

Application started

Telegram connected

New message received

Parsed values

Excel updated

Errors

8.

Use clean architecture.

Separate

Telegram logic

Parser

Excel

Configuration

Logging

9.

Handle reconnect automatically if Telegram disconnects.

10.

Code must be fully type hinted.

11.

Use dataclasses whenever appropriate.

12.

Use async/await correctly.

--------------------------------------------------
Parser
--------------------------------------------------

Parser must be independent.

Example

parse_message(text)

returns

ExchangeRate(
    buy=753,
    sell=755,
    cash=775
)

or None.

--------------------------------------------------
Excel
--------------------------------------------------

Create

data/exchange.xlsx

Header

Date | Time | Buy | Sell | Cash | Telegram Message ID | Raw Message

Append rows.

--------------------------------------------------
Logging
--------------------------------------------------

Use Python logging.

Console + File.

--------------------------------------------------
Requirements.txt
--------------------------------------------------

telethon
openpyxl
python-dotenv

--------------------------------------------------
Code Quality
--------------------------------------------------

Use

PEP8

Type hints

Docstrings

Comments only where necessary

No duplicated code

Reusable functions

--------------------------------------------------
Bonus Features
--------------------------------------------------

Also implement:

✔ Historical message download

When application starts

Download the latest 100 messages from the channel.

Insert only messages not already in Excel.

Then switch into live listening mode.

✔ Statistics

Print

Messages processed

Rows inserted

Rows skipped

✔ Graceful shutdown

Ctrl+C closes Telethon cleanly.

--------------------------------------------------
Expected Output
--------------------------------------------------

Generate the entire project.

Create every file.

Write complete code.

Do not leave TODOs.

The project should run after

pip install -r requirements.txt

python app.py

with only API_ID and API_HASH configured.