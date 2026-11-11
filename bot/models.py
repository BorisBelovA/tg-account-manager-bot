"""SQLAlchemy models.

Money is always stored as *positive integer minor units*; the transaction ``type``
('expense' | 'income') carries the direction.  Balances are derived from the ledger
and never stored, so they cannot drift.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(64), nullable=True)
    first_name = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    currency = Column(String(3), nullable=False)
    initial_balance = Column(Integer, nullable=False, default=0)
    created_by = Column(ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    members = relationship(
        "AccountMember", back_populates="account", cascade="all, delete-orphan"
    )
    transactions = relationship(
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )


class AccountMember(Base):
    __tablename__ = "account_members"

    account_id = Column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(16), nullable=False, default="member")  # 'owner' | 'member'
    joined_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    account = relationship("Account", back_populates="members")
    user = relationship("User")


class UserActiveAccount(Base):
    """Remembers which account a user is currently looking at."""

    __tablename__ = "user_active_accounts"

    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    account_id = Column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)


class Invite(Base):
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True)
    account_id = Column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(64), unique=True, index=True, nullable=False)
    created_by = Column(ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by = Column(ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    account_id = Column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id = Column(ForeignKey("users.id"), nullable=False)
    type = Column(String(16), nullable=False)  # 'expense' | 'income'
    amount = Column(Integer, nullable=False)  # positive, minor units
    category = Column(String(128), nullable=True)
    description = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    account = relationship("Account", back_populates="transactions")
    user = relationship("User")
