"""Functional flow test: drives the real handlers through a real FSM.

It patches nothing — it calls handler functions directly with lightweight fake
``Message``/``CallbackQuery`` objects and a real in-memory FSM context, against a
throwaway SQLite file. No Telegram token or network is needed.

Run from the project root:

    .venv\\Scripts\\python.exe flow_test.py
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

# Must be set before importing bot.* so the engine points at the throwaway DB.
os.environ["DATABASE_URL"] = "sqlite:///data/flow_test.db"

_DB_PATH = Path(__file__).resolve().parent / "data" / "flow_test.db"
if _DB_PATH.exists():
    _DB_PATH.unlink()

from sqlalchemy import select  # noqa: E402

from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.storage.base import StorageKey  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402

from bot.db import SessionLocal, init_db  # noqa: E402
from bot.handlers import account as account_handlers  # noqa: E402
from bot.handlers import balance as balance_handlers  # noqa: E402
from bot.handlers import transactions as tx_handlers  # noqa: E402
from bot.models import Account, Transaction  # noqa: E402
from bot.services.accounts import create_account, ensure_user  # noqa: E402
from bot.states import AddTransaction, CreateAccount  # noqa: E402


def check(condition: object, label: str) -> None:
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    print(f"ok - {label}")


class TgUser:
    def __init__(self, user_id: int, username: str | None = None, first_name: str = "Test"):
        self.id = user_id
        self.username = username
        self.first_name = first_name


class FakeMessage:
    def __init__(self, tg_user: TgUser, text: str | None = None):
        self.from_user = tg_user
        self.text = text
        self.sent: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None, **kwargs):  # noqa: ANN001
        self.sent.append((text, reply_markup))


class FakeCallback:
    def __init__(self, tg_user: TgUser, data: str, message: FakeMessage):
        self.from_user = tg_user
        self.data = data
        self.message = message
        self.answered: list[str | None] = []

    async def answer(self, text: str | None = None, show_alert: bool = False, **kwargs):  # noqa: ANN001
        self.answered.append(text)


def _all_transactions() -> list[Transaction]:
    with SessionLocal() as session:
        return list(session.scalars(select(Transaction).order_by(Transaction.id)).all())


async def main() -> None:
    init_db()

    alice = TgUser(1, "alice", "Alice")
    with SessionLocal() as session:
        user = ensure_user(session, alice)
        create_account(session, user, "Family", "EUR", 100000)  # €1000.00

    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    ctx = FSMContext(storage, key)

    # --- Flow 1: amount + trailing note + a brand new category -------------
    await tx_handlers._begin_transaction(FakeMessage(alice), alice, ctx, "expense", "12.50 coffee")
    check(await ctx.get_state() == AddTransaction.waiting_category.state, "flow1: category step")
    data = await ctx.get_data()
    check(data["tx_amount"] == 1250, "flow1: amount parsed to minor units")
    check(data.get("tx_note") == "coffee" and data.get("note_ready") is True, "flow1: note from command")
    check(data.get("category_options") == [], "flow1: no categories suggested yet")

    await tx_handlers.on_category_text(FakeMessage(alice, "Groceries"), ctx)
    check(await ctx.get_state() == AddTransaction.waiting_confirm.state, "flow1: new category -> confirm")

    await tx_handlers.on_tx_confirm(FakeCallback(alice, "tx:confirm", FakeMessage(alice)), ctx)
    check(await ctx.get_state() is None, "flow1: state cleared after confirm")

    rows = _all_transactions()
    check(len(rows) == 1, "flow1: one transaction stored")
    check(
        rows[0].amount == 1250 and rows[0].category == "Groceries" and rows[0].description == "coffee",
        "flow1: fields stored correctly",
    )

    # --- Flow 2: new expense, category skipped, typed note -----------------
    await tx_handlers._begin_transaction(FakeMessage(alice), alice, ctx, "expense", "5.00")
    data = await ctx.get_data()
    check("Groceries" in (data.get("category_options") or []), "flow2: existing category suggested")

    await tx_handlers.on_category_choice(
        FakeCallback(alice, "cat:skip", FakeMessage(alice)), ctx
    )
    check(await ctx.get_state() == AddTransaction.waiting_note.state, "flow2: skip category -> note step")

    await tx_handlers.on_note_text(FakeMessage(alice, "bus ticket"), ctx)
    check(await ctx.get_state() == AddTransaction.waiting_confirm.state, "flow2: note -> confirm")
    await tx_handlers.on_tx_confirm(FakeCallback(alice, "tx:confirm", FakeMessage(alice)), ctx)

    rows = _all_transactions()
    check(len(rows) == 2, "flow2: second transaction stored")
    check(rows[1].category is None and rows[1].description == "bus ticket", "flow2: no category, note kept")

    # --- Flow 3: pick an existing category from the keyboard ---------------
    await tx_handlers._begin_transaction(FakeMessage(alice), alice, ctx, "expense", "3.00")
    data = await ctx.get_data()
    options = data["category_options"]
    index = options.index("Groceries")
    await tx_handlers.on_category_choice(
        FakeCallback(alice, f"cat:{index}", FakeMessage(alice)), ctx
    )
    check(await ctx.get_state() == AddTransaction.waiting_note.state, "flow3: picked category -> note step")

    await tx_handlers.on_note_skip(FakeCallback(alice, "note:skip", FakeMessage(alice)), ctx)
    check(await ctx.get_state() == AddTransaction.waiting_confirm.state, "flow3: skip note -> confirm")
    await tx_handlers.on_tx_confirm(FakeCallback(alice, "tx:confirm", FakeMessage(alice)), ctx)

    rows = _all_transactions()
    check(len(rows) == 3 and rows[2].category == "Groceries", "flow3: existing category reused")

    # --- Flow 4: cancel leaves nothing behind ------------------------------
    await tx_handlers._begin_transaction(FakeMessage(alice), alice, ctx, "expense", "1.00")
    await tx_handlers.on_category_text(FakeMessage(alice, "Temp"), ctx)
    await tx_handlers.on_note_skip(FakeCallback(alice, "note:skip", FakeMessage(alice)), ctx)
    await tx_handlers.on_tx_cancel(FakeCallback(alice, "tx:cancel", FakeMessage(alice)), ctx)
    check(await ctx.get_state() is None, "flow4: cancel clears state")
    check(len(_all_transactions()) == 3, "flow4: cancel stored nothing")

    # --- Flow 5: invalid amount re-prompts --------------------------------
    await tx_handlers._begin_transaction(FakeMessage(alice), alice, ctx, "expense", "abc")
    check(await ctx.get_state() == AddTransaction.waiting_amount.state, "flow5: invalid amount -> prompt")
    await ctx.clear()

    # --- Flow 6: account creation via /create ----------------------------
    bob = TgUser(2, "bob", "Bob")
    bob_ctx = FSMContext(storage, StorageKey(bot_id=1, chat_id=2, user_id=2))
    await account_handlers.cmd_create(
        FakeMessage(bob), SimpleNamespace(args="Holiday"), bob_ctx
    )
    check(await bob_ctx.get_state() == CreateAccount.waiting_currency.state, "flow6: currency step")

    await account_handlers.on_currency_eur(
        FakeCallback(bob, "ccy:EUR", FakeMessage(bob)), bob_ctx
    )
    check(
        await bob_ctx.get_state() == CreateAccount.waiting_initial_balance.state,
        "flow6: initial balance step",
    )

    await account_handlers.on_initial_balance(FakeMessage(bob, "500"), bob_ctx)
    check(await bob_ctx.get_state() == CreateAccount.waiting_confirm.state, "flow6: confirm step")

    await account_handlers.on_create_confirm(
        FakeCallback(bob, "acct:create", FakeMessage(bob)), bob_ctx
    )
    check(await bob_ctx.get_state() is None, "flow6: state cleared")

    with SessionLocal() as session:
        account = session.scalars(select(Account).where(Account.name == "Holiday")).first()
    check(
        account is not None and account.initial_balance == 50000 and account.currency == "EUR",
        "flow6: account created with EUR 500.00",
    )

    # --- Flow 7: balance & history rendering ------------------------------
    out = FakeMessage(alice)
    await balance_handlers._send_balance(out, alice)
    text = out.sent[-1][0]
    check("Remaining balance" in text and "€979.50" in text, "flow7: balance rendered correctly")

    out = FakeMessage(alice)
    await balance_handlers._send_history(out, alice, "")
    history_text = out.sent[-1][0]
    check("Recent transactions" in history_text, "flow7: history rendered")

    print("\nAll flow tests passed")


if __name__ == "__main__":
    asyncio.run(main())
