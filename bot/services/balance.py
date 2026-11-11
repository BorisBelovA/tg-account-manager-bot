"""Service layer: balance and per-member aggregation."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import Account, AccountMember, Transaction, User


@dataclass
class MemberSpend:
    user_id: int
    first_name: str
    username: str | None
    expense: int
    income: int


def total_income(session: Session, account_id: int) -> int:
    value = session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id == account_id,
            Transaction.type == "income",
        )
    )
    return int(value or 0)


def total_expense(session: Session, account_id: int) -> int:
    value = session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id == account_id,
            Transaction.type == "expense",
        )
    )
    return int(value or 0)


def current_balance(session: Session, account: Account) -> int:
    return int(account.initial_balance) + total_income(session, account.id) - total_expense(
        session, account.id
    )


def member_totals(session: Session, account_id: int) -> list[MemberSpend]:
    """Expense/income totals per member, including members with no activity."""
    expense_case = case((Transaction.type == "expense", Transaction.amount), else_=0)
    income_case = case((Transaction.type == "income", Transaction.amount), else_=0)

    rows = session.execute(
        select(
            User.id,
            User.first_name,
            User.username,
            func.coalesce(func.sum(expense_case), 0),
            func.coalesce(func.sum(income_case), 0),
        )
        .join(AccountMember, AccountMember.user_id == User.id)
        .outerjoin(
            Transaction,
            (Transaction.user_id == User.id) & (Transaction.account_id == account_id),
        )
        .where(AccountMember.account_id == account_id)
        .group_by(User.id, User.first_name, User.username)
        .order_by(User.id)
    ).all()

    return [
        MemberSpend(
            user_id=user_id,
            first_name=first_name or "",
            username=username,
            expense=int(expense or 0),
            income=int(income or 0),
        )
        for user_id, first_name, username, expense, income in rows
    ]
