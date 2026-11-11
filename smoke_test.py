"""Offline smoke test — no Telegram token or network needed.

Run from the project root:

    .venv\\Scripts\\python.exe smoke_test.py
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bot.currency import format_money, parse_amount
from bot.models import Base, Transaction, User
from bot.services.accounts import (
    create_account,
    get_active_account,
    is_owner,
)
from bot.services.balance import current_balance, member_totals, total_expense, total_income
from bot.services.invites import accept_invite, create_invite


def check(condition: object, label: str) -> None:
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    print(f"ok - {label}")


def test_currency() -> None:
    check(parse_amount("12.50", "EUR") == 1250, "parse 12.50 EUR")
    check(parse_amount("12,50", "EUR") == 1250, "parse comma decimal")
    check(parse_amount("1 234,56", "EUR") == 123456, "parse spaced thousands")
    check(parse_amount("12.505", "EUR") == 1251, "round half up")
    check(parse_amount("1250", "USD") == 125000, "parse whole USD")
    check(format_money(1250, "EUR") == "€12.50", "format EUR")
    check(format_money(-1250, "USD") == "-$12.50", "format negative USD")

    for bad in ("0", "-5", "abc", "", "1.2.3"):
        try:
            parse_amount(bad, "EUR")
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")
    print("ok - invalid amounts rejected")


def test_database() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    with Session() as session:
        alice = User(telegram_id=1, username="alice", first_name="Alice")
        bob = User(telegram_id=2, username="bob", first_name="Bob")
        session.add_all([alice, bob])
        session.commit()

        account = create_account(session, alice, "Family", "EUR", 100000)  # 1000.00
        check(is_owner(session, account.id, alice.id), "alice is owner")
        check(get_active_account(session, alice).id == account.id, "active account set")

        invite = create_invite(session, account, alice)
        ok, joined, error = accept_invite(session, bob, invite.token)
        check(ok and joined is not None and error is None, "bob joined via invite")
        check(get_active_account(session, bob).id == account.id, "bob active account set")

        ok_again, _acc, _err = accept_invite(session, bob, invite.token)
        check(not ok_again, "invite is single-use")

        session.add_all(
            [
                Transaction(
                    account_id=account.id,
                    user_id=alice.id,
                    type="income",
                    amount=200000,
                    category="Salary",
                ),
                Transaction(
                    account_id=account.id,
                    user_id=alice.id,
                    type="expense",
                    amount=5000,
                    category="Groceries",
                ),
                Transaction(
                    account_id=account.id,
                    user_id=bob.id,
                    type="expense",
                    amount=2500,
                    category="Coffee",
                ),
            ]
        )
        session.commit()

        check(total_income(session, account.id) == 200000, "total income")
        check(total_expense(session, account.id) == 7500, "total expense")
        check(
            current_balance(session, account) == 100000 + 200000 - 7500,
            "balance math",
        )

        totals = {m.user_id: m for m in member_totals(session, account.id)}
        check(totals[alice.id].expense == 5000, "alice spend")
        check(totals[bob.id].expense == 2500, "bob spend")
        check(totals[bob.id].income == 0, "bob income empty")


def test_handlers_importable() -> None:
    """Importing every handler catches syntax/import/API mistakes early."""
    import bot.handlers.account  # noqa: F401
    import bot.handlers.balance  # noqa: F401
    import bot.handlers.common  # noqa: F401
    import bot.handlers.invite  # noqa: F401
    import bot.handlers.start  # noqa: F401
    import bot.handlers.transactions  # noqa: F401
    import bot.main  # noqa: F401

    from bot.handlers.transactions import normalize_category, recent_categories

    check(normalize_category("  groceries ") == "Groceries", "normalize category")

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        user = User(telegram_id=9, first_name="X")
        session.add(user)
        session.commit()
        account = create_account(session, user, "Cat", "EUR", 0)
        session.add_all(
            [
                Transaction(
                    account_id=account.id, user_id=user.id, type="expense", amount=100, category="Food"
                ),
                Transaction(
                    account_id=account.id, user_id=user.id, type="expense", amount=100, category="Travel"
                ),
                Transaction(
                    account_id=account.id, user_id=user.id, type="expense", amount=100, category="food"
                ),
            ]
        )
        session.commit()
        cats = recent_categories(session, account.id, 8)
        check("Food" in cats and "Travel" in cats, "recent categories")


def main() -> None:
    test_currency()
    test_database()
    test_handlers_importable()
    print("\nAll smoke tests passed")


if __name__ == "__main__":
    main()
