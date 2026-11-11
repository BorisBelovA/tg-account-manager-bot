"""Configuration loaded from environment variables / .env file."""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")


def _resolve_database_url(url: str) -> str:
    """Turn a relative sqlite URL into an absolute one anchored at the project root."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    raw = url[len(prefix):]
    if raw.startswith("/") or raw.startswith("file:"):
        return url
    if raw == ":memory:":
        return url
    if re.match(r"^[A-Za-z]:/", raw):
        return url  # absolute Windows path already in URL form
    path = (BASE_DIR / raw).resolve()
    return "sqlite:///" + path.as_posix()


BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
DATABASE_URL = _resolve_database_url((os.getenv("DATABASE_URL") or "sqlite:///data/bot.db").strip())
LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
REPORT_TZ = (os.getenv("REPORT_TZ") or "Europe/Nicosia").strip()

# The SQLite database lives here by default; make sure the folder exists.
DATA_DIR.mkdir(parents=True, exist_ok=True)
