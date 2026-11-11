"""/create, /accounts, /setbalance and their callback flows."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..currency import format_money, parse_amount
from ..db import SessionLocal
from ..handlers.filters import is_switch_callback, not_command
from ..keyboards import (
    accounts_keyboard,
    confirm_account_keyboard,
    currency_keyboard,
    main_menu,
)
from ..models import Account
from ..services.accounts import (
    create_account,
    ensure_user,
    get_active_account,
    is_member,
    is_owner,
    list_user_accounts,
    set_active_account,
)
from ..services.balance import current_balance
from ..states import CreateAccount, SetBalance
from ..utils import h

router = Router(name="account")


def _try_parse(text: str, currency: str) -> int | None:
    try:
        return parse_amount(text, currency)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# /create
# ---------------------------------------------------------------------------
@router.message(Command("create"))
async def cmd_create(message: Message, command: CommandObject, state: FSMContext) -> None:
    name = (command.args or "").strip()
    if len(name) > 120:
        await message.answer("That name is too long (max 120 characters).")
        return

    await state.clear()
    if not name:
        await state.set_state(CreateAccount.waiting_name)
        await message.answer("What should the account be called? Send a name.")
        return

    await state.update_data(account_name=name)
    await state.set_state(CreateAccount.waiting_currency)
    await message.answer(
        f"Creating <b>{h(name)}</b>.\n\nChoose the account currency:",
        reply_markup=currency_keyboard(),
    )


@router.message(CreateAccount.waiting_name, F.text, not_command)
async def on_account_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Please send a non-empty name.")
        return
    if len(name) > 120:
        await message.answer("That name is too long (max 120 characters).")
        return
    await state.update_data(account_name=name)
    await state.set_state(CreateAccount.waiting_currency)
    await message.answer(
        f"Creating <b>{h(name)}</b>.\n\nChoose the account currency:",
        reply_markup=currency_keyboard(),
    )


async def _choose_currency(callback: CallbackQuery, state: FSMContext, code: str) -> None:
    await state.update_data(currency=code)
    await state.set_state(CreateAccount.waiting_initial_balance)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"Currency: <b>{code}</b>.\n\n"
            "What is the current balance of that bank account? "
            "Send an amount, e.g. <code>1250.00</code>."
        )


@router.callback_query(CreateAccount.waiting_currency, F.data == "ccy:EUR")
async def on_currency_eur(callback: CallbackQuery, state: FSMContext) -> None:
    await _choose_currency(callback, state, "EUR")


@router.callback_query(CreateAccount.waiting_currency, F.data == "ccy:USD")
async def on_currency_usd(callback: CallbackQuery, state: FSMContext) -> None:
    await _choose_currency(callback, state, "USD")


@router.message(CreateAccount.waiting_initial_balance, F.text, not_command)
async def on_initial_balance(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    currency = data.get("currency") or "EUR"
    amount = _try_parse(message.text or "", currency)
    if amount is None:
        await message.answer("⚠️ Send a valid amount, e.g. <code>1250.00</code>.")
        return

    await state.update_data(initial_balance=amount)
    await state.set_state(CreateAccount.waiting_confirm)
    name = data.get("account_name") or "Account"
    await message.answer(
        "Please confirm:\n\n"
        f"<b>{h(name)}</b>\n"
        f"Currency: <b>{currency}</b>\n"
        f"Starting balance: <b>{format_money(amount, currency)}</b>",
        reply_markup=confirm_account_keyboard(),
    )


@router.callback_query(CreateAccount.waiting_confirm, F.data == "acct:create")
async def on_create_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    name = (data.get("account_name") or "").strip()
    currency = data.get("currency")
    initial_balance = data.get("initial_balance")
    if not name or not currency or initial_balance is None:
        await callback.answer("Something went wrong — please start again.", show_alert=True)
        await state.clear()
        return

    with SessionLocal() as session:
        user = ensure_user(session, callback.from_user)
        account = create_account(session, user, name, currency, int(initial_balance))
        account_name = account.name
        account_currency = account.currency
        starting = account.initial_balance

    await state.clear()
    await callback.answer("Account created ✅")
    if callback.message:
        await callback.message.answer(
            f"✅ Account <b>{h(account_name)}</b> created.\n"
            f"Starting balance: <b>{format_money(starting, account_currency)}</b>\n\n"
            "Invite another member with /invite.",
            reply_markup=main_menu(),
        )


# ---------------------------------------------------------------------------
# /accounts
# ---------------------------------------------------------------------------
async def _send_accounts(message: Message, tg_user) -> None:
    with SessionLocal() as session:
        user = ensure_user(session, tg_user)
        items = list_user_accounts(session, user.id)
        active = get_active_account(session, user)
        active_id = active.id if active else None
        rows = [
            (acc.id, acc.name, acc.currency, acc.id == active_id)
            for acc, _role in items
        ]

    if not rows:
        await message.answer("You don't have any accounts yet. Create one with /create.")
        return
    await message.answer("Your accounts (tap one to switch):", reply_markup=accounts_keyboard(rows))


@router.message(Command("accounts"))
async def cmd_accounts(message: Message) -> None:
    await _send_accounts(message, message.from_user)


@router.callback_query(F.data == "menu:accounts")
async def cb_accounts(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await _send_accounts(callback.message, callback.from_user)


@router.callback_query(is_switch_callback)
async def on_switch_account(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        account_id = int((callback.data or "")[len("switch:") :])
    except ValueError:
        await callback.answer("Bad account id.", show_alert=True)
        return

    with SessionLocal() as session:
        user = ensure_user(session, callback.from_user)
        if not is_member(session, account_id, user.id):
            await callback.answer("You are not a member of that account.", show_alert=True)
            return
        account = session.get(Account, account_id)
        if account is None:
            await callback.answer("Account not found.", show_alert=True)
            return
        set_active_account(session, user, account.id)
        name = account.name
        currency = account.currency

    await state.clear()
    await callback.answer(f"Switched to {name}")
    if callback.message:
        await callback.message.answer(f"✅ Active account: <b>{h(name)}</b> ({currency})")


# ---------------------------------------------------------------------------
# /setbalance
# ---------------------------------------------------------------------------
async def _apply_new_balance(
    message: Message, account_id: int, currency: str, amount: int
) -> None:
    with SessionLocal() as session:
        account = session.get(Account, account_id)
        if account is None:
            await message.answer("Account not found.")
            return
        account.initial_balance = amount
        session.commit()
        balance = current_balance(session, account)
        name = account.name
        actual_currency = account.currency

    await message.answer(
        f"✅ Starting balance for <b>{h(name)}</b> set to "
        f"<b>{format_money(amount, actual_currency)}</b>.\n"
        f"💰 Remaining: <b>{format_money(balance, actual_currency)}</b>"
    )


@router.message(Command("setbalance"))
async def cmd_setbalance(
    message: Message, command: CommandObject, state: FSMContext
) -> None:
    with SessionLocal() as session:
        user = ensure_user(session, message.from_user)
        account = get_active_account(session, user)
        if account is None:
            await message.answer("You don't have an account yet. Create one with /create.")
            return
        if not is_owner(session, account.id, user.id):
            await message.answer("Only the account owner can change the starting balance.")
            return
        account_id = account.id
        currency = account.currency

    raw = (command.args or "").strip()
    if not raw:
        await state.set_state(SetBalance.waiting_amount)
        await state.update_data(
            setbalance_account_id=account_id, setbalance_currency=currency
        )
        await message.answer(
            f"Send the new starting balance in <b>{currency}</b>, e.g. <code>1250.00</code>:"
        )
        return

    amount = _try_parse(raw, currency)
    if amount is None:
        await message.answer("⚠️ Send a valid amount, e.g. <code>1250.00</code>.")
        return
    await _apply_new_balance(message, account_id, currency, amount)


@router.message(SetBalance.waiting_amount, F.text, not_command)
async def on_setbalance_amount(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    account_id = data.get("setbalance_account_id")
    currency = data.get("setbalance_currency") or "EUR"
    if account_id is None:
        await state.clear()
        await message.answer("Something went wrong. Try /setbalance again.")
        return

    amount = _try_parse(message.text or "", currency)
    if amount is None:
        await message.answer("⚠️ Send a valid amount, e.g. <code>1250.00</code>.")
        return

    await state.clear()
    await _apply_new_balance(message, int(account_id), currency, amount)


# ---------------------------------------------------------------------------
# Cancel buttons
# ---------------------------------------------------------------------------
async def _cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Cancelled")
    if callback.message:
        await callback.message.answer("Cancelled. ✅")


@router.callback_query(F.data == "flow:cancel")
async def on_flow_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _cancel_flow(callback, state)


@router.callback_query(F.data == "acct:cancel")
async def on_acct_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _cancel_flow(callback, state)
