"""Small shared helpers."""
from __future__ import annotations

from html import escape


def h(text: str | None) -> str:
    """Escape arbitrary text for Telegram HTML parse mode.

    Telegram supports the named entities ``&lt;``, ``&gt;`` and ``&amp;`` only,
    so quotes are intentionally left untouched (``quote=False``).
    """
    return escape(text or "", quote=False)
