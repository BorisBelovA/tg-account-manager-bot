"""Routing test: feeds fake Telegram updates through the real aiogram dispatcher.

The bot's HTTP layer is mocked, so no token or network is needed. This exercises
the actual router order, filters, FSM state lookup and handler wiring.

Run from the project root:

    .venv\\Scripts\\python.exe routing_test.py
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///data/routing_test.db"

_DB_PATH = Path(__file__).resolve().parent / "data" / "routing_test.db"
if _DB_PATH.exists():
    _DB_PATH.unlink()

from aiogram import Bot  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.storage.base import StorageKey  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Message, Update, User  # noqa: E402

from bot.db import init_db  # noqa: E402
from bot.main import create_dispatcher  # noqa: E402


def check(condition: object, label: str) -> None:
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    print(f"ok - {label}")


class Recorder:
    """Stand-in for the Bot API session; records outgoing methods."""

    def __init__(self) -> None:
        self.methods: list[object] = []

    async def __call__(self, bot, method, timeout=None):  # noqa: ANN001
        self.methods.append(method)
        return {}


async def main() -> None:
    init_db()
    bot = Bot(token="123:TEST")
    recorder = Recorder()
    bot.session.make_request = recorder  # type: ignore[method-assign]
    dp = create_dispatcher()

    user = User(id=1, is_bot=False, first_name="Alice")
    chat = Chat(id=1, type="private")
    now = datetime.now(timezone.utc)
    counter = {"n": 0}

    def make_message(text: str) -> Message:
        return Message(message_id=counter["n"], date=now, chat=chat, from_user=user, text=text)

    async def send_text(text: str) -> None:
        counter["n"] += 1
        await dp.feed_update(bot, Update(update_id=counter["n"], message=make_message(text)))

    async def send_callback(data: str) -> None:
        counter["n"] += 1
        query = CallbackQuery(
            id=str(counter["n"]),
            from_user=user,
            chat_instance="ci",
            data=data,
            message=make_message(""),
        )
        await dp.feed_update(bot, Update(update_id=counter["n"], callback_query=query))

    def last_text() -> str:
        for method in reversed(recorder.methods):
            text = getattr(method, "text", None)
            if text:
                return str(text)
        return ""

    ctx = FSMContext(
        dp.storage,
        StorageKey(bot_id=bot.id, chat_id=chat.id, user_id=user.id),
    )

    # 1. /start registers the user and shows the menu.
    await send_text("/start")
    check("Welcome" in last_text(), "routing: /start handled")

    # 2. /create sets up the currency step.
    await send_text("/create Family")
    check("Choose the account currency" in last_text(), "routing: /create prompts currency")

    # 3. Currency callback advances to the balance step.
    await send_callback("ccy:EUR")
    check("What is the current balance" in last_text(), "routing: currency callback handled")
    check(
        await ctx.get_state() == "CreateAccount:waiting_initial_balance",
        "routing: FSM state advanced",
    )

    # 4. Initial balance text is accepted.
    await send_text("500")
    check("Please confirm" in last_text(), "routing: initial balance accepted")

    # 5. Confirm callback creates the account.
    await send_callback("acct:create")
    check("created" in last_text().lower(), "routing: account created")

    # 6. /balance shows the starting bank balance.
    await send_text("/balance")
    check("Remaining balance" in last_text() and "€500.00" in last_text(), "routing: balance shows €500.00")

    # 7. /spend prompts for a category (no categories yet).
    await send_text("/spend 12.50")
    check("Choose a category" in last_text(), "routing: /spend prompts category")

    # 8. Skipping the category moves to the note step.
    await send_callback("cat:skip")
    check("note" in last_text().lower(), "routing: category skip -> note step")

    # 9. Typing a note moves to confirmation.
    await send_text("lunch")
    check("Please confirm" in last_text(), "routing: note -> confirm step")

    # 10. Confirming records the expense.
    await send_callback("tx:confirm")
    check("recorded" in last_text().lower(), "routing: transaction recorded")

    # 11. Balance reflects the expense.
    await send_text("/balance")
    check("€487.50" in last_text(), "routing: balance after expense is €487.50")

    # 12. /spend without an amount asks for one.
    await send_text("/spend")
    check("How much is the expense" in last_text(), "routing: /spend without amount prompts")

    # 13. /cancel clears the pending flow.
    await send_text("/cancel")
    check("Cancelled" in last_text(), "routing: /cancel clears state")
    check(await ctx.get_state() is None, "routing: state is clear after /cancel")

    # 14. A command is not swallowed by an active FSM text step.
    await send_text("/spend")
    await send_text("/help")
    check("Shared expense bot" in last_text(), "routing: /help not swallowed by FSM")

    print("\nAll routing tests passed")


if __name__ == "__main__":
    asyncio.run(main())
