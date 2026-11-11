"""Custom aiogram filters used across handlers."""
from __future__ import annotations

from aiogram.types import CallbackQuery, Message


def not_command(message: Message) -> bool:
    """True for free text that is not a slash command."""
    text = message.text or ""
    return bool(text) and not text.startswith("/")


def is_category_callback(callback: CallbackQuery) -> bool:
    return bool(callback.data) and callback.data.startswith("cat:")


def is_switch_callback(callback: CallbackQuery) -> bool:
    return bool(callback.data) and callback.data.startswith("switch:")
