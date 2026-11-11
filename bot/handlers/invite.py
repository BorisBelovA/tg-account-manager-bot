"""/invite — owner generates a single-use deep link for another member."""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from ..db import SessionLocal
from ..services.accounts import ensure_user, get_active_account, is_owner
from ..services.invites import create_invite
from ..utils import h

router = Router(name="invite")


@router.message(Command("invite"))
async def cmd_invite(message: Message, bot: Bot) -> None:
    with SessionLocal() as session:
        user = ensure_user(session, message.from_user)
        account = get_active_account(session, user)
        if account is None:
            await message.answer("Create an account first with <code>/create &lt;name&gt;</code>.")
            return
        if not is_owner(session, account.id, user.id):
            await message.answer("Only the account owner can invite new members.")
            return
        invite = create_invite(session, account, user)
        account_name = account.name
        token = invite.token

    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=invite_{token}"
    await message.answer(
        f"Invite someone to <b>{h(account_name)}</b>:\n\n"
        f"{link}\n\n"
        "The link works once and expires in 7 days."
    )
