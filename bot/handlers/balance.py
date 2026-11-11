"""/balance and /history."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from ..currency import format_money
from ..db import SessionLocal
from ..models import Transaction, User
from ..services.accounts import ensure_user, get_active_account
from ..services.balance import current_balance, member_totals
from ..utils import h

router = Router(name="balance")


async def _send_balance(message: Message, tg_user) -> None:
    with SessionLocal() as session:
        user = ensure_user(session, tg_user)
        account = get_active_account(session, user)
        if account is None:
            await message.answer("You don't have an account yet. Create one with /create.")
            return
        balance = current_balance(session, account)
        totals = member_totals(session, account.id)
        currency = account.currency
        name = account.name
        initial = account.initial_balance

    lines = [
        f"🏦 <b>{h(name)}</b>",
        f"Starting balance: <b>{format_money(initial, currency)}</b>",
        f"Remaining balance: <b>{format_money(balance, currency)}</b>",
        "",
        "<b>Who spent what</b>",
    ]
    if not totals:
        lines.append("No activity yet.")
    for member in totals:
        label = member.first_name or member.username or "User"
        line = f"• {h(label)}: spent <b>{format_money(member.expense, currency)}</b>"
        if member.income:
            line += f" · income <b>{format_money(member.income, currency)}</b>"
        lines.append(line)

    await message.answer("\n".join(lines))


async def _send_history(message: Message, tg_user, args: str) -> None:
    limit = 10
    stripped = (args or "").strip()
    if stripped.isdigit():
        limit = max(1, min(50, int(stripped)))

    with SessionLocal() as session:
        user = ensure_user(session, tg_user)
        account = get_active_account(session, user)
        if account is None:
            await message.answer("You don't have an account yet. Create one with /create.")
            return
        rows = session.execute(
            select(Transaction, User)
            .join(User, User.id == Transaction.user_id)
            .where(Transaction.account_id == account.id)
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
            .limit(limit)
        ).all()
        currency = account.currency

    if not rows:
        await message.answer("No transactions yet. Record one with /spend.")
        return

    lines = ["🧾 <b>Recent transactions</b>", ""]
    for tx, tx_user in rows:
        sign = "−" if tx.type == "expense" else "+"
        when = ""
        if tx.created_at is not None:
            try:
                when = tx.created_at.astimezone().strftime("%d %b %H:%M") + " · "
            except (ValueError, OSError):
                when = ""
        label = tx_user.first_name or tx_user.username or "User"
        parts = [
            f"{when}{h(label)} · {sign}{format_money(tx.amount, currency)}"
        ]
        extra = []
        if tx.category:
            extra.append(h(tx.category))
        if tx.description:
            extra.append(h(tx.description))
        if extra:
            parts.append("(" + " · ".join(extra) + ")")
        lines.append(" • ".join(parts))

    await message.answer("\n".join(lines))


@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    await _send_balance(message, message.from_user)


@router.callback_query(F.data == "menu:balance")
async def cb_balance(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await _send_balance(callback.message, callback.from_user)


@router.message(Command("history"))
async def cmd_history(message: Message, command: CommandObject) -> None:
    await _send_history(message, message.from_user, command.args or "")


@router.callback_query(F.data == "menu:history")
async def cb_history(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await _send_history(callback.message, callback.from_user, "")
