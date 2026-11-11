"""Add expense / income flows with category suggestions."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from ..currency import format_money, parse_amount
from ..db import SessionLocal
from ..handlers.filters import is_category_callback, not_command
from ..keyboards import (
    category_keyboard,
    note_keyboard,
    transaction_confirm_keyboard,
)
from ..models import Account, Transaction
from ..services.accounts import ensure_user, get_active_account, is_member
from ..services.balance import current_balance
from ..states import AddTransaction
from ..utils import h

router = Router(name="transactions")

MAX_CATEGORY_SUGGESTIONS = 8


def recent_categories(session, account_id: int, limit: int) -> list[str]:
    rows = session.execute(
        select(Transaction.category, func.max(Transaction.created_at))
        .where(
            Transaction.account_id == account_id,
            Transaction.category.is_not(None),
            Transaction.category != "",
        )
        .group_by(Transaction.category)
        .order_by(func.max(Transaction.created_at).desc())
        .limit(limit)
    ).all()
    return [str(row[0]) for row in rows if row[0]]


def normalize_category(raw: str) -> str:
    text = " ".join(raw.split())
    if len(text) > 64:
        text = text[:64].rstrip()
    if not text:
        return ""
    return text[0].upper() + text[1:]


def _try_parse(text: str, currency: str) -> int | None:
    try:
        return parse_amount(text, currency)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
async def _begin_transaction(
    message: Message,
    tg_user,
    state: FSMContext,
    tx_type: str,
    raw_args: str,
) -> None:
    with SessionLocal() as session:
        user = ensure_user(session, tg_user)
        account = get_active_account(session, user)
        if account is None:
            await message.answer("You need an account first — create one with /create.")
            return
        account_id = account.id
        currency = account.currency

    await state.clear()
    await state.update_data(tx_type=tx_type, account_id=account_id, currency=currency)

    raw = (raw_args or "").strip()
    amount: int | None = None
    note: str | None = None
    if raw:
        # Try the whole string first so "1 234,56" is read as one amount.
        amount = _try_parse(raw, currency)
        if amount is None:
            first, _sep, rest = raw.partition(" ")
            amount = _try_parse(first, currency)
            if amount is not None and rest.strip():
                note = rest.strip()[:500]

    if amount is None:
        await state.set_state(AddTransaction.waiting_amount)
        if raw:
            await message.answer("⚠️ Send a valid amount, e.g. <code>12.50</code>.")
        else:
            label = "expense" if tx_type == "expense" else "income"
            await message.answer(
                f"How much is the {label}? Send an amount, e.g. <code>12.50</code>."
            )
        return

    await state.update_data(tx_amount=amount)
    if note:
        await state.update_data(tx_note=note, note_ready=True)
    await _show_category_step(message, state)


@router.message(Command("spend"))
async def cmd_spend(message: Message, command: CommandObject, state: FSMContext) -> None:
    await _begin_transaction(message, message.from_user, state, "expense", command.args or "")


@router.message(Command("income"))
async def cmd_income(message: Message, command: CommandObject, state: FSMContext) -> None:
    await _begin_transaction(message, message.from_user, state, "income", command.args or "")


@router.message(Command("skip"))
async def cmd_skip(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current == AddTransaction.waiting_category.state:
        await state.update_data(tx_category=None)
        await _after_category(message, state)
    elif current == AddTransaction.waiting_note.state:
        await state.update_data(tx_note=None, note_ready=True)
        await _show_confirm_step(message, state)
    else:
        await message.answer("Nothing to skip.")


@router.callback_query(F.data == "menu:spend:expense")
async def cb_menu_expense(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message:
        await _begin_transaction(callback.message, callback.from_user, state, "expense", "")


@router.callback_query(F.data == "menu:spend:income")
async def cb_menu_income(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message:
        await _begin_transaction(callback.message, callback.from_user, state, "income", "")


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------
async def _show_category_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    with SessionLocal() as session:
        categories = recent_categories(session, account_id, MAX_CATEGORY_SUGGESTIONS)

    await state.update_data(category_options=categories)
    await state.set_state(AddTransaction.waiting_category)
    await message.answer(
        "Choose a category, or type a new one:",
        reply_markup=category_keyboard(categories),
    )


async def _after_category(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("note_ready"):
        await _show_confirm_step(message, state)
    else:
        await _show_note_step(message, state)


async def _show_note_step(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTransaction.waiting_note)
    await message.answer(
        "Add a short note? (optional)\nSend text, or press Skip.",
        reply_markup=note_keyboard(),
    )


async def _show_confirm_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    amount = int(data.get("tx_amount", 0))
    currency = data.get("currency", "EUR")
    tx_type = data.get("tx_type", "expense")
    category = data.get("tx_category")
    note = data.get("tx_note")

    label = "Expense" if tx_type == "expense" else "Income"
    lines = [f"<b>{label}</b> {format_money(amount, currency)}"]
    meta = []
    if category:
        meta.append(h(category))
    if note:
        meta.append(h(note))
    if meta:
        lines.append(" · ".join(meta))

    await state.set_state(AddTransaction.waiting_confirm)
    await message.answer(
        "Please confirm:\n\n" + "\n".join(lines),
        reply_markup=transaction_confirm_keyboard(),
    )


# ---------------------------------------------------------------------------
# Text input steps
# ---------------------------------------------------------------------------
@router.message(AddTransaction.waiting_amount, F.text, not_command)
async def on_tx_amount(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    currency = data.get("currency") or "EUR"
    amount = _try_parse(message.text or "", currency)
    if amount is None:
        await message.answer("⚠️ Send a valid amount, e.g. <code>12.50</code>.")
        return
    await state.update_data(tx_amount=amount)
    await _show_category_step(message, state)


@router.message(AddTransaction.waiting_category, F.text, not_command)
async def on_category_text(message: Message, state: FSMContext) -> None:
    category = normalize_category(message.text or "")
    if not category:
        await message.answer("Send a category name, or press Skip.")
        return
    await state.update_data(tx_category=category)
    await _after_category(message, state)


@router.message(AddTransaction.waiting_note, F.text, not_command)
async def on_note_text(message: Message, state: FSMContext) -> None:
    note = (message.text or "").strip()
    if not note:
        await message.answer("Send a note, or press Skip.")
        return
    await state.update_data(tx_note=note[:500], note_ready=True)
    await _show_confirm_step(message, state)


# ---------------------------------------------------------------------------
# Callback steps
# ---------------------------------------------------------------------------
@router.callback_query(AddTransaction.waiting_category, is_category_callback)
async def on_category_choice(callback: CallbackQuery, state: FSMContext) -> None:
    payload = (callback.data or "")[len("cat:") :]

    if payload == "skip":
        await state.update_data(tx_category=None)
        await callback.answer()
        if callback.message:
            await _after_category(callback.message, state)
        return

    if payload == "new":
        await callback.answer()
        if callback.message:
            await callback.message.answer("Send the new category name:")
        return

    data = await state.get_data()
    options = data.get("category_options") or []
    try:
        category = options[int(payload)]
    except (ValueError, IndexError, TypeError):
        await callback.answer("That option is no longer available.", show_alert=True)
        return

    await state.update_data(tx_category=category)
    await callback.answer()
    if callback.message:
        await _after_category(callback.message, state)


@router.callback_query(AddTransaction.waiting_note, F.data == "note:skip")
async def on_note_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(tx_note=None, note_ready=True)
    await callback.answer()
    if callback.message:
        await _show_confirm_step(callback.message, state)


@router.callback_query(AddTransaction.waiting_confirm, F.data == "tx:confirm")
async def on_tx_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        account_id = int(data["account_id"])
        amount = int(data["tx_amount"])
        tx_type = str(data["tx_type"])
    except (KeyError, TypeError, ValueError):
        await callback.answer("Session expired — please start again.", show_alert=True)
        await state.clear()
        return

    if tx_type not in ("expense", "income"):
        await callback.answer("Invalid entry type.", show_alert=True)
        await state.clear()
        return

    category = data.get("tx_category")
    note = data.get("tx_note")

    with SessionLocal() as session:
        user = ensure_user(session, callback.from_user)
        account = session.get(Account, account_id)
        if account is None or not is_member(session, account.id, user.id):
            await callback.answer("You are not a member of this account.", show_alert=True)
            await state.clear()
            return
        session.add(
            Transaction(
                account_id=account.id,
                user_id=user.id,
                type=tx_type,
                amount=amount,
                category=category,
                description=note,
            )
        )
        session.commit()
        balance = current_balance(session, account)
        currency = account.currency

    await state.clear()
    await callback.answer("Recorded ✅")
    if callback.message:
        label = "Expense" if tx_type == "expense" else "Income"
        text = f"✅ {label} recorded: <b>{format_money(amount, currency)}</b>"
        if category:
            text += f" · {h(category)}"
        if note:
            text += f" · {h(note)}"
        text += f"\n💰 Remaining balance: <b>{format_money(balance, currency)}</b>"
        await callback.message.answer(text)


@router.callback_query(AddTransaction.waiting_confirm, F.data == "tx:cancel")
async def on_tx_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Cancelled")
    if callback.message:
        await callback.message.answer("Cancelled. ✅")
