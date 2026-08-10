"""Shared money primitives.

`Decimal("0")` was redeclared as a private `_ZERO` in five service modules.
Money in this app is `Decimal` end to end — `Numeric(15, 2)` columns, `Decimal`
in the service layer, and `str(...)` at the JSON boundary — so the zero literal
belongs in one place alongside the helpers that operate on it.
"""

from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")

_CENTS = Decimal("0.01")


def money_str(value: Decimal) -> str:
    """Serialize a monetary Decimal as a fixed 2-decimal-place string.

    Bare `str(Decimal)` preserves whatever scale the value happens to carry, so
    the same response could contain "0" (from a scaleless ZERO constant),
    "3000.00" (from a Numeric(15, 2) column), and "3000.0" (from a value that
    had passed through a float). Clients parse all three fine, but the wire
    format should not depend on which arithmetic path produced the number.
    """
    return str(value.quantize(_CENTS, rounding=ROUND_HALF_UP))


def signed_balance(normal_balance: str, debits: Decimal, credits: Decimal) -> Decimal:
    """Net a debit/credit pair into the account's natural sign.

    Debit-normal accounts (assets, expenses) increase with debits; credit-normal
    accounts (liabilities, equity, income) increase with credits. Returning the
    balance already signed for the account's side means callers never have to
    re-derive the rule — it previously existed as three separate copies in
    reconciliation, statements, and dashboard.
    """
    if normal_balance == "debit":
        return debits - credits
    return credits - debits
