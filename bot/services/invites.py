"""Service layer: invite tokens."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, AccountMember, Invite, User
from .accounts import is_member, set_active_account

INVITE_TTL_DAYS = 7


def create_invite(session: Session, account: Account, creator: User) -> Invite:
    invite = Invite(
        account_id=account.id,
        token=secrets.token_urlsafe(12),
        created_by=creator.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(invite)
    session.commit()
    return invite


def accept_invite(
    session: Session, user: User, token: str
) -> tuple[bool, Account | None, str | None]:
    """Try to join the account behind ``token``. Returns (ok, account, error)."""
    invite = session.scalar(select(Invite).where(Invite.token == token))
    if invite is None:
        return False, None, "That invite link is not valid."
    if invite.accepted_by is not None:
        return False, None, "This invite has already been used."
    if invite.expires_at is not None:
        expires = invite.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            return False, None, "This invite link has expired."

    account = session.get(Account, invite.account_id)
    if account is None:
        return False, None, "That account no longer exists."

    if not is_member(session, account.id, user.id):
        session.add(
            AccountMember(account_id=account.id, user_id=user.id, role="member")
        )
    invite.accepted_by = user.id
    session.commit()
    set_active_account(session, user, account.id)
    return True, account, None
