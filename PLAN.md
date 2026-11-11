# Telegram Shared Expense Bot — Implementation Plan

> Status: Design (pre-code). Stack locked: **Python 3.12 + aiogram 3.x + SQLAlchemy 2.x + SQLite → PostgreSQL**.
> Currency is chosen **per account at creation time**.

---

## 1. Problem & Goal

Two (or more) people spend from **one shared bank account** and the bank app has no
good way to split/track who spent what. The bot gives a shared ledger in Telegram:

- Each member records **expenses** and **incomes** from their phone.
- The bot computes the **live remaining balance** and **how much each member spent**.
- No double-entry complexity, no money actually moves — it is a *tracking* tool, not a payment tool.

### Non-goals (explicitly out of scope)

- Actual money transfers / payments between members.
- Bank API integration (manual initial balance, manual reconciliation).
- Multi-currency *within* one account (an account has exactly one currency).
- FX conversion between accounts.
- Group-chat posting — members interact with the bot in a **private chat only**.

---

## 2. Scope

### Iteration 1 — MVP (must have)

1. Register a Telegram user with the bot.
2. Create a shared **Account**: set name, **choose currency**, set initial balance.
3. Invite another Telegram user via deep link; they join as a member.
4. Record expenses and incomes (amount + note + category, with category **suggested from previously used ones** — §7.1).
5. Show remaining balance and per-member spend breakdown.
6. List recent transactions.
7. Adjust the starting balance (`/setbalance`).
8. Basic validation and friendly error messages.

### Iteration 2 — reports & analytics (deferred)

1. Weekly / monthly automated summaries (scheduled).
2. `/report week|month` — totals by category and by member.
3. Trend charts, top categories, me-vs-them comparison (matplotlib images).
4. CSV export.
5. Reconciliation flow (`/reconcile` to correct drift vs. real bank balance).

---

## 3. Architecture overview

```
 Telegram client (you + brother)
        │  messages / callback queries
        ▼
  aiogram bot (long-polling)
        │
        ▼
  Service layer  (balance calc, invites, reports)
        │
        ▼
  SQLAlchemy ORM
        │
        ▼
  SQLite (MVP) ──► PostgreSQL (production)
```

- **Single process**, long-polling for MVP (no public URL / webhook needed).
- **Service layer** keeps balance and aggregation logic in one place, so both the
  bot handlers and (later) scheduled reports use the same code.
- **FSM (aiogram `StatesGroup`)** drives multi-step flows: create account, add
  transaction with category, etc.

---

## 4. Domain model

```
users
  id            PK
  telegram_id   BIGINT UNIQUE   (the identity that matters)
  username      TEXT NULL
  first_name    TEXT
  created_at    TIMESTAMP

accounts
  id                PK
  name              TEXT
  currency          CHAR(3)          ISO 4217, e.g. "EUR"
  initial_balance   INTEGER          minor units (see §5)
  created_by        FK -> users.id   (owner)
  created_at        TIMESTAMP

account_members
  account_id    FK -> accounts.id   ┐ PK (account_id, user_id)
  user_id       FK -> users.id      ┘
  role          TEXT                'owner' | 'member'
  joined_at     TIMESTAMP

invites
  id            PK
  account_id    FK -> accounts.id
  token         TEXT UNIQUE         random, single-use
  created_by    FK -> users.id
  expires_at    TIMESTAMP NULL
  accepted_by   FK -> users.id NULL

transactions
  id            PK
  account_id    FK -> accounts.id
  user_id       FK -> users.id      who recorded it
  type          TEXT                'expense' | 'income'
  amount        INTEGER             minor units (always positive)
  category      TEXT NULL           normalized title-case; powers suggestions
  description   TEXT NULL
  created_at    TIMESTAMP

# No separate categories table in iter 1 — the suggestion list is derived from
# existing transactions (see §7.1). A dedicated table (emoji icons / rename) is
# an optional iter-2 refinement.
```

- A user may belong to **many** accounts; an account has **many** members (many-to-many).
- `transactions.user_id` records *who entered the entry* — this powers the
  per-member spend breakdown. It is not who "owns" the money (money is shared).
- `transactions.amount` is stored as a **positive integer**; `type` gives the sign.
  Never store a signed amount — it invites sign bugs.
- Category suggestions come from **previously used values** (`DISTINCT category`),
  not a predefined list — see §7.1.

---

## 5. Currency handling (chosen at account creation)

Requirement: user picks the currency when creating the account.

### Storage rule

- Store amounts as **integer minor units** (e.g. EUR `12.50` → `1250`).
- The number of decimals differs per currency (EUR=2, JPY=0, BHD=3), so we keep a
  small lookup table of ISO 4217 codes:

```python
CURRENCIES = {
    "EUR": {"exponent": 2, "symbol": "€", "name": "Euro"},
    "USD": {"exponent": 2, "symbol": "$", "name": "US Dollar"},
    # add more here as needed (e.g. JPY has exponent 0, BHD has exponent 3)
}
```

- Unknown codes fall back to `exponent: 2` with a warning to the user.
- Every formatting / parsing path goes through two helpers so the exponent logic
  lives in **one place**:

```python
to_minor("12.50", "EUR")  -> 1250          # parse user input, round to exponent
format_money(1250, "EUR") -> "€12.50"      # display
```

- An account has **one** currency; all its transactions and its balance are in that
  currency. No mixing, no conversion.

### Create-account UX for currency

```
/create "Family"
  └─ Step 1: name (already given) 
  └─ Step 2: currency — inline keyboard: **EUR / USD** (extensible via CURRENCIES table)
  └─ Step 3: initial balance (parse with the chosen currency's exponent)
  └─ Step 4: confirmation card → create
```

---

## 6. Balance & aggregation rules

All figures are **derived by query**, never stored, so concurrent edits can't drift:

```
remaining_balance(account) =
      initial_balance
    + SUM(amount WHERE type='income')
    − SUM(amount WHERE type='expense')

spent_by_member(account, user) =
      SUM(amount WHERE type='expense' AND user_id = user)

earned_by_member(account, user) =
      SUM(amount WHERE type='income' AND user_id = user)
```

- `initial_balance` is an integer minor-unit value stored on the account.
- `/setbalance <amount>` rewrites `initial_balance`; because the ledger is unchanged,
  this is safe and idempotent.
- Iteration 2 `/reconcile` will compute an **adjustment** transaction so the full
  audit trail is preserved instead of silently overwriting.

---

## 7. Command reference

### Iteration 1

| Command | Example | Effect |
|---|---|---|
| `/start` | — | Register user, show main menu (inline keyboard) |
| `/create <name>` | `/create Family` | Start create-account flow (currency → initial balance → confirm) |
| `/invite` | — | Generate join link for the current account |
| `/spend <amount>` | `/spend 12.50` | Start expense flow (category → note → confirm) |
| `/income <amount>` | `/income 1500` | Start income flow (category → note → confirm) |
| `/setbalance <amount>` | `/setbalance 800` | Rewrite the starting balance |
| `/balance` | — | Remaining balance + per-member breakdown |
| `/history [n]` | `/history 10` | Last n transactions (default 10) |
| `/accounts` | — | List accounts the user belongs to; switch active account |
| `/help` | — | Command reference |

### Account context

Because a user may belong to several accounts, the bot keeps an **active account**
per user. `/accounts` switches it. For MVP with one shared account this is mostly
invisible, but the model supports it from day one.

### 7.1 Add-transaction flow (category suggestions)

Requirement: the category input is matched against **previously used categories** —
day 1 you type "Groceries"; day 2 you can pick "Groceries" from a shortcut or type
a new one.

```
/spend 12.50
```
1. **Amount** parsed (bot asks for it if missing).
2. **Category** — inline keyboard:
   - up to 8 previously used categories for this account, most-recent first,
   - "➕ New category" → FSM prompt to type a name,
   - "Skip" (category optional).
3. **Note** (optional description) — or `/skip`.
4. **Confirmation card** — "Expense €12.50 · Groceries · coffee" with ✅/❌.

- Suggestion query:
  `SELECT category, MAX(created_at) FROM transactions WHERE account_id = ? AND category IS NOT NULL GROUP BY category ORDER BY MAX(created_at) DESC LIMIT 8`
- Categories are normalized to title-case on save ("groceries" → "Groceries") to
  reduce near-duplicates.
- The list is **per account**, so both members see the same "Groceries" shortcut.
- Iteration 2 (optional): promote to a real `categories` table with emoji icons and
  rename support.

### Iteration 2

| Command | Effect |
|---|---|
| `/report week` / `/report month` | Aggregated totals by category + by member |
| `/export` | CSV of transactions |
| `/reconcile <actual>` | Add adjustment so remaining matches the real bank balance |
| (scheduled) | Weekly/monthly digest messages |

---

## 8. Invite / onboarding flow (deep link)

```
You:              /invite
Bot:              t.me/YourBot?start=invite_<TOKEN>   (single-use token)
You:              forward link to brother
Brother:          clicks link → opens bot with /start invite_<TOKEN>
Bot:              registers brother (if new) → adds him to account as 'member'
Brother:          sees confirmation "You joined <account>"
```

- Tokens are **single-use** and optionally expire (default 7 days).
- Only the account **owner** (or later, members with permission) can invite.
- Deep-link payloads are routed in the `/start` handler: `start=invite_<TOKEN>`.

---

## 9. Permissions / roles

| Action | owner | member |
|---|---|---|
| Add expense / income | ✅ | ✅ |
| View balance / history | ✅ | ✅ |
| Invite | ✅ | ❌ (iter 1) |
| Edit name / set balance | ✅ | ❌ (iter 1) |
| Delete account / remove member | ✅ | ❌ (iter 2) |

Iteration 1 keeps roles binary and minimal; iteration 2 can add "editor" vs
"viewer" if needed.

---

## 10. Validation & error handling

- **Amount parsing**: accept `12.50`, `12,50`, `12` (comma = decimal separator);
  reject negatives, zero, and nonsense; round to the currency's exponent.
- **Currency**: validate ISO code; unknown → confirm default 2 decimals.
- **Membership checks**: every mutating handler verifies the user is a member of
  the active account.
- **Token checks**: expired / used / unknown invite tokens → clear error.
- **Idempotency**: double-tapping a confirm button must not create two
  transactions (compare against a pending FSM state / de-dupe on callback id).
- Friendly, non-crashy responses; unexpected errors are logged with a generic
  "something went wrong" reply.

---

## 11. Concurrency & data integrity

- Two users (or one user double-tapping) can race. Balance is computed by `SUM`,
  so it self-heals; the risk is only *duplicate or lost* rows.
- Mitigations: single SQLite writer + short transactions; de-dupe confirm
  callbacks; `BEGIN IMMEDIATE` for writes. For PostgreSQL later, use row locks or
  serializable isolation for `/reconcile`.

---

## 12. Time handling

- Store all timestamps in **UTC** (`TIMESTAMP WITH TIME ZONE`).
- Convert to the user's timezone for display; the bot tracks each user's tz
  (default Europe/Nicosia, changeable via `/settimezone` in iter 2).
- Weekly/monthly reports must use the *user's* local week/month boundaries.

---

## 13. Configuration & environment

```
BOT_TOKEN=123456:ABC...        # from @BotFather
DATABASE_URL=sqlite:///data/bot.db     # or postgresql+psycopg://...
LOG_LEVEL=INFO
REPORT_TZ=Europe/Nicosia       # default for scheduled reports
```

- Secrets never committed; `.env` is git-ignored, `.env.example` is committed.
- SQLite file lives under `data/` (persisted volume on cloud hosts).

---

## 14. Project structure

```
tg-expense-bot/
├─ bot/
│  ├─ __init__.py
│  ├─ main.py                 # entrypoint, dispatcher, polling
│  ├─ config.py               # env loading
│  ├─ db.py                   # engine, session factory
│  ├─ models.py               # SQLAlchemy models
│  ├─ currency.py             # CURRENCIES table + to_minor/format_money
│  ├─ handlers/
│  │  ├─ start.py             # /start + deep-link routing
│  │  ├─ account.py           # /create, /accounts, /setbalance
│  │  ├─ invite.py            # /invite, invite acceptance
│  │  ├─ transactions.py      # /spend, /income, /history
│  │  └─ balance.py           # /balance
│  ├─ services/
│  │  ├─ balance.py           # aggregation queries
│  │  ├─ invites.py           # token generation/validation
│  │  └─ accounts.py          # membership checks, active-account
│  ├─ states.py               # aiogram StatesGroups (FSM)
│  └─ keyboards.py            # inline keyboards
├─ migrations/                # Alembic (or SQLAlchemy create_all for MVP)
├─ data/                      # SQLite file (git-ignored)
├─ .env.example
├─ .gitignore
├─ pyproject.toml
├─ README.md
└─ PLAN.md                    # this document
```

---

## 15. Iteration 2 — reports & analytics design (preview)

- **Aggregator service** computes totals by `[account, period, group_by]`
  (`group_by ∈ {member, category}`).
- **Scheduler** (APScheduler, or a system cron hitting a CLI) fires the weekly and
  monthly digests; **each member receives the digest in their own DM** with the bot.
- **Charts**: matplotlib → PNG sent as `InputFile`; bars for categories, line for
  trend, side-by-side for me-vs-them.
- **CSV export**: `transactions` joined with users, formatted in the account
  currency, ISO dates.
- **Reconciliation**: `/reconcile 812.33` inserts a synthetic `adjustment` row so
  the audit trail is intact.

---

## 16. Deployment options

| Option | Notes |
|---|---|
| Own PC / Raspberry Pi | Simplest; run with `systemd`/`pm2` + long polling; keep SQLite |
| Railway / Render / Fly.io | Free tier; attach persistent volume for SQLite, or swap to Postgres |
| VPS (Hetzner/DigitalOcean) | Cheapest reliable; Docker or systemd + Postgres |

Recommended path: **start on your PC with SQLite**, graduate to Railway/Render +
Postgres when you want it always-on.

---

## 17. Milestones & acceptance criteria

1. **M1 — scaffold**: bot answers `/start`, registers user. ✅ `/start` stores a `users` row.
2. **M2 — accounts**: `/create` FSM collects name + currency + initial balance. ✅ account row with correct `initial_balance` minor units.
3. **M3 — invites**: `/invite` deep link joins a second user. ✅ two `account_members` rows.
4. **M4 — ledger**: `/spend`, `/income` (with category suggestions), `/balance`, `/history`. ✅ balance math matches hand calculation incl. per-member totals.
5. **M5 — hardening**: parsing, validation, error handling, de-dupe. ✅ malformed input never crashes; no duplicate rows.
6. **M6 — iter 2**: scheduled weekly/monthly reports. ✅ digest arrives on schedule with correct totals.
7. **M7 — iter 2**: analytics + charts + CSV. ✅ charts and CSV match the ledger.

---

## 18. Resolved decisions

1. **Invite permission** — account **owner only** in iteration 1.
2. **Category UX** — suggestions from **previously used categories** (type a new
   one or pick an existing one) — §7.1.
3. **Group chat** — **out of scope**. Members send expenses directly to the bot in
   a private chat only.
4. **Reports destination** — weekly/monthly digest goes to **each member's DM**.
5. **Currency list** — **EUR and USD** for now; the `CURRENCIES` table makes adding
   more trivial.

---

## 19. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Float rounding corrupts money | Integer minor units + single formatting helper |
| Double-tap creates duplicate expense | FSM state + callback de-dupe |
| Two people edit concurrently | Balance derived by `SUM`; short write transactions |
| Free host wipes SQLite file | Persistent volume, or Postgres on a managed host |
| Deep-link invite abused | Single-use, expiring tokens; membership check on accept |
