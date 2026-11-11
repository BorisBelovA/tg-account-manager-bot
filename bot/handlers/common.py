"""Global commands that must be reachable while any flow is running."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

router = Router(name="common")

HELP_TEXT = (
    "<b>Shared expense bot</b>\n\n"
    "<b>Money</b>\n"
    "/spend &lt;amount&gt; [note] — record an expense\n"
    "/income &lt;amount&gt; [note] — record an income\n"
    "/balance — remaining balance and per-person spend\n"
    "/history [n] — last transactions (default 10)\n\n"
    "<b>Accounts</b>\n"
    "/create &lt;name&gt; — create a shared account\n"
    "/invite — invite another member (owner only)\n"
    "/accounts — switch active account\n"
    "/setbalance &lt;amount&gt; — set the starting balance (owner only)\n\n"
    "<b>Other</b>\n"
    "/cancel — cancel the current action\n"
    "/skip — skip an optional step\n"
    "/help — show this message"
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(HELP_TEXT)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Nothing to cancel.")
        return
    await state.clear()
    await message.answer("Cancelled. ✅")
