"""Inline keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Add expense", callback_data="menu:spend:expense"),
                InlineKeyboardButton(text="➕ Add income", callback_data="menu:spend:income"),
            ],
            [
                InlineKeyboardButton(text="📊 Balance", callback_data="menu:balance"),
                InlineKeyboardButton(text="🧾 History", callback_data="menu:history"),
            ],
            [
                InlineKeyboardButton(text="📁 Accounts", callback_data="menu:accounts"),
                InlineKeyboardButton(text="❓ Help", callback_data="menu:help"),
            ],
        ]
    )


def currency_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="EUR €", callback_data="ccy:EUR"),
                InlineKeyboardButton(text="USD $", callback_data="ccy:USD"),
            ],
            [InlineKeyboardButton(text="✖ Cancel", callback_data="flow:cancel")],
        ]
    )


def confirm_account_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Create account", callback_data="acct:create"),
                InlineKeyboardButton(text="✖ Cancel", callback_data="acct:cancel"),
            ],
        ]
    )


def category_keyboard(categories: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, name in enumerate(categories):
        row.append(InlineKeyboardButton(text=name, callback_data=f"cat:{idx}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="➕ New category", callback_data="cat:new"),
            InlineKeyboardButton(text="⏭ Skip", callback_data="cat:skip"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def note_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Skip note", callback_data="note:skip")],
        ]
    )


def transaction_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data="tx:confirm"),
                InlineKeyboardButton(text="✖ Cancel", callback_data="tx:cancel"),
            ],
        ]
    )


def accounts_keyboard(accounts: list[tuple[int, str, str, bool]]) -> InlineKeyboardMarkup:
    """``accounts`` items are ``(id, name, currency, is_active)``."""
    rows: list[list[InlineKeyboardButton]] = []
    for account_id, name, currency, active in accounts:
        prefix = "✅ " if active else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{name} ({currency})",
                    callback_data=f"switch:{account_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
