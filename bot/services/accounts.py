"""Service layer: account membership and active-account bookkeeping."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, AccountMember, User, UserActiveAccount


def get_user_by_telegram_id(session: Session, telegram_id: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_id == telegram_id))


def get_or_create_user(
    session: Session,
    telegram_id: int,
    username: str | None,
    first_name: str,
) -> tuple[User, bool]:
    """Return (user, created). Refreshes username/first name when they change."""
    user = get_user_by_telegram_id(session, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name or "")
        session.add(user)
        session.commit()
        return user, True

    changed = False
    if username and user.username != username:
        user.username = username
        changed = True
    if first_name and user.first_name != first_name:
        user.first_name = first_name
        changed = True
    if changed:
        session.commit()
    return user, False


def ensure_user(session: Session, tg_user: Any) -> User:
    """Convenience wrapper around :func:`get_or_create_user` for handler callers."""
    user, _ = get_or_create_user(
        session,
        tg_user.id,
        getattr(tg_user, "username", None),
        getattr(tg_user, "first_name", "") or "",
    )
    return user


def is_member(session: Session, account_id: int, user_id: int) -> bool:
    return session.get(AccountMember, (account_id, user_id)) is not None


def membership_role(session: Session, account_id: int, user_id: int) -> str | None:
    member = session.get(AccountMember, (account_id, user_id))
    return member.role if member is not None else None


def is_owner(session: Session, account_id: int, user_id: int) -> bool:
    return membership_role(session, account_id, user_id) == "owner"


def set_active_account(session: Session, user: User, account_id: int) -> None:
    row = session.get(UserActiveAccount, user.id)
    if row is None:
        session.add(UserActiveAccount(user_id=user.id, account_id=account_id))
    else:
        row.account_id = account_id
    session.commit()


def get_active_account(session: Session, user: User) -> Account | None:
    """Return the user's selected account, falling back to their first membership."""
    row = session.get(UserActiveAccount, user.id)
    if row is not None:
        account = session.get(Account, row.account_id)
        if account is not None and is_member(session, account.id, user.id):
            return account

    membership = session.scalar(
        select(AccountMember)
        .where(AccountMember.user_id == user.id)
        .order_by(AccountMember.joined_at)
        .limit(1)
    )
    if membership is None:
        return None
    account = session.get(Account, membership.account_id)
    if account is not None:
        set_active_account(session, user, account.id)
    return account


def list_user_accounts(session: Session, user_id: int) -> list[tuple[Account, str]]:
    rows = session.execute(
        select(Account, AccountMember.role)
        .join(AccountMember, AccountMember.account_id == Account.id)
        .where(AccountMember.user_id == user_id)
        .order_by(Account.created_at)
    ).all()
    return [(account, role) for account, role in rows]


def create_account(
    session: Session,
    user: User,
    name: str,
    currency: str,
    initial_balance: int,
) -> Account:
    account = Account(
        name=name.strip(),
        currency=currency.upper(),
        initial_balance=initial_balance,
        created_by=user.id,
    )
    session.add(account)
    session.flush()
    session.add(AccountMember(account_id=account.id, user_id=user.id, role="owner"))
    session.commit()
    set_active_account(session, user, account.id)
    return account
