"""Bot entry point.

Run from the project root::

    python -m bot.main
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import BOT_TOKEN, LOG_LEVEL
from .db import init_db
from .handlers import account, balance, common, invite, start, transactions
from .menu import setup_menu_button

logger = logging.getLogger(__name__)


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    # Order matters: `common` must come first so /cancel and /help are always reachable.
    dispatcher.include_router(common.router)
    dispatcher.include_router(start.router)
    dispatcher.include_router(account.router)
    dispatcher.include_router(invite.router)
    dispatcher.include_router(transactions.router)
    dispatcher.include_router(balance.router)
    return dispatcher


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is not set.\n"
            "Open `.env` and paste the token you got from @BotFather."
        )

    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await setup_menu_button(bot)
    dispatcher = create_dispatcher()
    logger.info("Starting long polling…")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
