# Shared Expense Telegram Bot

A Telegram bot for tracking spending on a **shared bank account**. Two (or more)
people record expenses and incomes; the bot keeps the remaining balance and shows
how much each person has spent.

> This is an *accounting* tool — it never moves money and needs no bank integration.

## Features (iteration 1)

- Create a shared account with a chosen currency (**EUR** or **USD**) and a starting balance.
- Invite another Telegram user with a single-use deep link (owner only).
- Record expenses and incomes with a **category suggested from previously used ones**.
- See the remaining balance and a per-member spending breakdown.
- Browse recent transactions.
- Adjust the starting balance.
- **Persistent menu button** (bottom-left of the message field) with every operation one tap away.

## Requirements

- **Python 3.11+** (developed against 3.12).
- A bot token from [@BotFather](https://t.me/BotFather).

> **Windows note:** the bare `python` command on this machine resolves to the
> Microsoft Store stub, which prints `Python` (or opens the Store) instead of
> running anything. Always call the venv interpreter directly
> (`.\.venv\Scripts\python.exe …`), activate the venv first, or just use `.\run.cmd`.

## Setup

```powershell
# 1. From the project root, create a virtual environment
py -m venv .venv

# 2. Install dependencies into it
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. Open .env and paste your BOT_TOKEN
#    (if .env is missing: Copy-Item .env.example .env)

# 4. Run the bot
.\run.cmd
# equivalent to:
# .\.venv\Scripts\python.exe -m bot.main
```

Stop the bot with `Ctrl+C`.

## Commands

| Command | Description |
|---|---|
| `/start` | Register and show the main menu |
| `/menu` | Open the main menu (also available via the persistent menu button) |
| `/create <name>` | Create a shared account (choose EUR/USD, then starting balance) |
| `/invite` | Generate a single-use join link (owner only) |
| `/spend <amount> [note]` | Record an expense |
| `/income <amount> [note]` | Record an income |
| `/balance` | Remaining balance + per-member spend |
| `/history [n]` | Last `n` transactions (default 10) |
| `/accounts` | List and switch the active account |
| `/setbalance <amount>` | Set the starting balance (owner only) |
| `/skip` | Skip an optional step |
| `/cancel` | Cancel the current action |
| `/help` | Command reference |

Amounts accept `12.50`, `12,50` and `1 234,56`.

## Menu button

On startup the bot registers its command catalog with Telegram and sets the chat
menu button to **Commands**.  That is the small button at the bottom-left of the
message field in Telegram clients; tapping it always shows the account and money
operations — no need to remember slash commands or scroll back to `/start`.

The catalog lives in `bot/menu.py`, so adding an operation there is enough.  No
BotFather configuration is required.  If Telegram is unreachable at startup the
bot logs a warning and keeps working; the button is configured on the next start.

## How the numbers work

- Each amount is stored as an **integer in minor units** (`€12.50` → `1250`), so there
  are no float rounding errors.
- Every account has exactly one currency; decimals follow that currency.
- The balance is **derived**, never stored:

  ```
  remaining = initial_balance + Σ incomes − Σ expenses
  ```

- Per-member spending is `Σ expenses grouped by the person who recorded them`.

## Project layout

```
bot/
├─ main.py          # entry point, router wiring, polling
├─ config.py        # .env loading
├─ db.py            # engine + session factory
├─ models.py        # SQLAlchemy models
├─ currency.py      # minor-unit parsing / formatting
├─ keyboards.py     # inline keyboards
├─ menu.py          # persistent menu button + command catalog
├─ states.py        # FSM state groups
├─ utils.py         # HTML escaping
├─ handlers/        # common, start, account, invite, transactions, balance
└─ services/        # accounts, invites, balance aggregation
smoke_test.py       # currency, DB services, imports
flow_test.py        # handler + FSM flows
routing_test.py     # dispatcher routing/filters (mocked HTTP)
```

## Verifying the install (offline)

Three scripts run without a token or network:

```powershell
python smoke_test.py     # currency math, DB services, handler imports
python flow_test.py      # handler + FSM flows against a throwaway DB
python routing_test.py   # real aiogram routing/filters, HTTP layer mocked
```

They create temporary databases under `data/` (git-ignored).

## Roadmap (iteration 2)

- Weekly / monthly automated summaries to each member's DM.
- `/report week|month` with totals by category and member.
- Trend charts, top categories, CSV export.
- Reconciliation (`/reconcile`) against the real bank balance.

See `PLAN.md` for the full design document.
