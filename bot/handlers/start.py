"""/start, first-time registration and invite deep-link handling."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..db import SessionLocal
from ..keyboards import main_menu
from ..services.accounts import get_or_create_user
from ..services.invites import accept_invite
from ..utils import h

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()
    tg_user = message.from_user

    with SessionLocal() as session:
        user, created = get_or_create_user(
            session, tg_user.id, tg_user.username, tg_user.first_name or ""
        )

        if command.args and command.args.startswith("invite_"):
            token = command.args[len("invite_") :]
            ok, account, error = accept_invite(session, user, token)
            if ok and account is not None:
                text = (
                    f"✅ You joined <b>{h(account.name)}</b> ({account.currency}).\n\n"
                    "Use /balance to see where things stand."
                )
            else:
                text = f"⚠️ {h(error or 'Could not join that account.')}"
        elif created:
            text = (
                "👋 Welcome! I help you and your partner track spending on a shared bank account.\n\n"
                "<b>Get started:</b>\n"
                "1. Create an account with <code>/create Family</code>\n"
                "2. Invite the other person with /invite\n"
                "3. Record money with /spend and /income\n\n"
                "Tip: /help lists every command."
            )
        else:
            text = "👋 Welcome back! What would you like to do?"

    await message.answer(text, reply_markup=main_menu())
