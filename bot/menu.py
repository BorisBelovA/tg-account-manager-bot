"""Persistent Telegram menu button.

Telegram shows a small menu button at the bottom-left of the message input in
private chats.  Configured as ``MenuButtonCommands`` it opens the bot's command
list — the native way to keep the operations one tap away on every screen.

The commands below are what users see in that list; order is top-to-bottom.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    MenuButtonCommands,
)

logger = logging.getLogger(__name__)

# Account operations first, then money operations, then help.
BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="menu", description="☰ Open the main menu"),
    BotCommand(command="accounts", description="📁 Switch active account"),
    BotCommand(command="create", description="➕ Create a shared account"),
    BotCommand(command="invite", description="👥 Invite a member"),
    BotCommand(command="setbalance", description="🏦 Set the starting balance"),
    BotCommand(command="spend", description="➖ Add an expense"),
    BotCommand(command="income", description="💰 Add an income"),
    BotCommand(command="balance", description="📊 Show the balance"),
    BotCommand(command="history", description="🧾 Recent transactions"),
    BotCommand(command="help", description="❓ Help"),
    BotCommand(command="cancel", description="✖ Cancel the current action"),
)


async def setup_menu_button(bot: Bot) -> None:
    """Register the command list and switch on the persistent menu button.

    Called once at startup.  Failure is non-fatal: the bot remains usable via
    commands and inline keyboards even if Telegram is briefly unreachable.
    """
    try:
        await bot.set_my_commands(
            commands=list(BOT_COMMANDS),
            scope=BotCommandScopeAllPrivateChats(),
        )
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logger.info("Menu button configured with %d commands", len(BOT_COMMANDS))
    except Exception:  # noqa: BLE001 - menu setup must never block startup
        logger.exception("Failed to set up the Telegram menu button")
