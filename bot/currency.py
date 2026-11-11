"""Currency helpers: ISO-4217 table and minor-unit conversions.

All money in the database is stored as **integer minor units** — e.g. EUR 12.50
is stored as ``1250`` — so there are no floating point rounding errors.

The account's currency decides how many decimals a value has (the exponent):
EUR/USD use 2, JPY would use 0, BHD would use 3.  Only EUR and USD are enabled
for account creation right now; add more entries to ``CURRENCIES`` to enable them.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CURRENCIES: dict[str, dict[str, object]] = {
    "EUR": {"exponent": 2, "symbol": "€", "name": "Euro"},
    "USD": {"exponent": 2, "symbol": "$", "name": "US Dollar"},
}

DEFAULT_EXPONENT = 2


def is_supported_currency(code: str) -> bool:
    return (code or "").upper() in CURRENCIES


def currency_exponent(code: str) -> int:
    meta = CURRENCIES.get((code or "").upper())
    if not meta:
        return DEFAULT_EXPONENT
    return int(meta["exponent"])  # type: ignore[arg-type]


def currency_symbol(code: str) -> str:
    meta = CURRENCIES.get((code or "").upper())
    if not meta:
        return (code or "").upper()
    return str(meta["symbol"])


def _normalise_decimal(text: str) -> str:
    text = str(text).strip().replace(" ", "").replace("\u00a0", "")
    if not text:
        raise ValueError("Amount is empty.")
    has_dot = "." in text
    has_comma = "," in text
    if has_dot and has_comma:
        # Whichever separator comes last is the decimal separator.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        text = text.replace(",", ".")
    return text


def parse_amount(text: str, currency: str) -> int:
    """Parse a human amount into integer minor units.

    Accepts ``12.50``, ``12,50`` and spaced thousands like ``1 234,56``.
    Raises :class:`ValueError` for invalid or non-positive input.
    """
    normalised = _normalise_decimal(text)
    try:
        value = Decimal(normalised)
    except InvalidOperation as exc:
        raise ValueError("That doesn't look like a number.") from exc
    if not value.is_finite():
        raise ValueError("That doesn't look like a number.")
    if value <= 0:
        raise ValueError("Amount must be greater than zero.")

    exponent = currency_exponent(currency)
    quantum = Decimal(1).scaleb(-exponent)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    minor = int(rounded.scaleb(exponent))
    if minor <= 0:
        raise ValueError("Amount must be greater than zero.")
    return minor


def format_money(minor: int, currency: str) -> str:
    """Render minor units for display, e.g. ``€12.50`` or ``-$5.00``."""
    exponent = currency_exponent(currency)
    symbol = currency_symbol(currency)
    negative = minor < 0
    value = Decimal(abs(int(minor))).scaleb(-exponent)
    body = f"{value:,.{exponent}f}"
    return f"{'-' if negative else ''}{symbol}{body}"


def format_plain(minor: int, currency: str) -> str:
    """Render minor units with the currency code, e.g. ``12.50 EUR`` (CSV friendly)."""
    exponent = currency_exponent(currency)
    value = Decimal(int(minor)).scaleb(-exponent)
    return f"{value:.{exponent}f} {currency.upper()}"
