"""Deterministic CSV/XLSX → ExtractedTxn mapping.

Resolution happens in two tiers. Tier 1 is the alias matching below: headers are
folded through `scrub.normalize_header`, so ``Post Date``, ``post_date`` and
``POST-DATE`` are the same column, and a layout is described by a `ColumnMapping`
rather than by three hard-coded indices. It covers every export seen so far:

  - Bank OZK CSV (old): ``Date, Description, ChkRef, Amount, Balance``
    Amount is a string like ``"$2,569.00 "`` or ``"($25.00)"`` (parens = negative).
  - Bank OZK CSV (new): ``Account Number, Post Date, Check, Description, Debit,
    Credit, Status, Balance`` — no signed Amount column; the sign comes from which
    of Debit/Credit is populated, and non-posted rows are dropped.
  - EJ Mastercard XLSX: ``Date, Transaction, Name, Memo, Amount``
    Amount is already a numeric Excel value (negative = charge).

Tier 2, in the `*_async` entry points, hands an unrecognized header row to
`app.agents.statement.run_schema_mapper` and applies whatever mapping it returns.
The agent only ever names columns — every date and amount is still decoded by the
functions here — so a bad mapping cannot silently alter a number, and the sample
rows it sees are redacted first.

Extending the alias tuples is still the cheapest fix for a new format; the agent
is the safety net for a layout nobody has extended for yet.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from app.agents.statement import ExtractedTxn, ResolvedColumns, run_schema_mapper
from app.core.config import settings
from app.services.file_readers import ParseError
from app.services.scrub import (
    is_sensitive_column,
    normalize_header,
    redact_columns,
    scrub_text,
)

logger = logging.getLogger(__name__)

DATE_ALIASES: tuple[str, ...] = (
    "date", "transaction date", "posted date", "post date", "posting date",
    "trans date", "effective date", "date posted",
)
# Order is priority, not just membership: the first match wins, so a real
# "Description" column beats the "Name"/"Memo" pair on the EJ export.
DESC_ALIASES: tuple[str, ...] = (
    "description", "transaction description", "details", "narrative",
    "payee", "merchant", "name", "memo", "transaction",
)
AMOUNT_ALIASES: tuple[str, ...] = ("amount", "transaction amount", "net amount")
DEBIT_ALIASES: tuple[str, ...] = (
    "debit", "debits", "withdrawal", "withdrawals", "money out", "charge", "charges",
)
CREDIT_ALIASES: tuple[str, ...] = (
    "credit", "credits", "deposit", "deposits", "money in", "payment", "payments",
)
STATUS_ALIASES: tuple[str, ...] = ("status", "transaction status")

# Everything else — "pending", "authorized", "hold" — is a row the bank may still
# reverse, and posting it would double-count once the settled row arrives.
POSTED_VALUES: tuple[str, ...] = ("posted", "cleared", "settled", "complete", "completed")

DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%-m/%-d/%y",
    "%-m/%-d/%Y",
    "%m-%d-%Y",
)


@dataclass(frozen=True)
class ColumnMapping:
    """A resolved layout: which column means what, and how to read its sign."""

    date_col: str
    desc_cols: tuple[str, ...]
    amount_col: str | None = None
    debit_col: str | None = None
    credit_col: str | None = None
    debit_is_negative: bool = True
    status_col: str | None = None
    posted_values: tuple[str, ...] = POSTED_VALUES


def _norm(s: Any) -> str:
    return normalize_header(s)


def _pick(headers: Sequence[str], aliases: tuple[str, ...]) -> str | None:
    """Return the first header matching an alias, in alias-priority order."""
    lookup = {_norm(h): h for h in headers}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    return None


def _coerce_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        raise ParseError("Empty date value")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"Unrecognized date format: {text!r}")


def _coerce_amount(value: Any) -> Decimal:
    """Parse an amount string or Decimal. Handles ``$1,234.56`` and ``(12.34)`` (= -12.34)."""
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip()
    if not text:
        raise ParseError("Empty amount")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = re.sub(r"[\$,\s]", "", text)
    if not text:
        raise ParseError("Empty amount after stripping symbols")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ParseError(f"Unrecognized amount format: {value!r}") from exc
    return -amount if negative else amount


def _resolve_columns(headers: Sequence[str]) -> ColumnMapping | None:
    """Match headers against the alias tuples. ``None`` means "ask the agent".

    Returning None rather than raising is what lets the caller fall through to
    tier 2; the sync entry points turn it back into a `ParseError`.
    """
    date_col = _pick(headers, DATE_ALIASES)
    desc_col = _pick(headers, DESC_ALIASES)
    if not date_col or not desc_col:
        return None

    amount_col = _pick(headers, AMOUNT_ALIASES)
    debit_col = _pick(headers, DEBIT_ALIASES)
    credit_col = _pick(headers, CREDIT_ALIASES)

    if amount_col:
        return ColumnMapping(
            date_col=date_col,
            desc_cols=(desc_col,),
            amount_col=amount_col,
            status_col=_pick(headers, STATUS_ALIASES),
        )
    if debit_col and credit_col:
        return ColumnMapping(
            date_col=date_col,
            desc_cols=(desc_col,),
            debit_col=debit_col,
            credit_col=credit_col,
            status_col=_pick(headers, STATUS_ALIASES),
        )
    return None


def _cell(row: Sequence[Any], i: int) -> Any:
    """Value at `i`, or None past the end of a short row.

    Rows are routinely ragged: openpyxl drops trailing empty cells, so a row whose
    last columns are blank is simply shorter than the header. Indexing it directly
    would fail the whole document over a missing empty string.
    """
    return row[i] if i < len(row) else None


def _row_amount(mapping: ColumnMapping, row: Sequence[Any], idx: dict[str, int]) -> Decimal | None:
    """Signed amount for one row, or None when the row carries no amount at all."""
    if mapping.amount_col:
        return _coerce_amount(_cell(row, idx[mapping.amount_col]))

    def side(col: str | None) -> Decimal:
        if not col:
            return Decimal("0")
        raw = _cell(row, idx[col])
        if raw is None or str(raw).strip() == "":
            return Decimal("0")
        # abs(): a bank that writes its debits as "-160.00" inside a column already
        # named Debit must not have the sign applied twice.
        return abs(_coerce_amount(raw))

    debit, credit = side(mapping.debit_col), side(mapping.credit_col)
    if debit == 0 and credit == 0:
        return None
    return credit - debit if mapping.debit_is_negative else debit - credit


def _apply_mapping(
    mapping: ColumnMapping, headers: Sequence[str], data_rows: Sequence[Sequence[Any]]
) -> list[ExtractedTxn]:
    missing = [
        c
        for c in (
            mapping.date_col, *mapping.desc_cols, mapping.amount_col,
            mapping.debit_col, mapping.credit_col, mapping.status_col,
        )
        if c is not None and c not in headers
    ]
    if missing:
        raise ParseError(f"Mapped columns not present in the file: {missing}. Headers: {list(headers)}")

    # `RawTransaction.description` is stored verbatim by design, so an identifier
    # column selected as the description would persist an account number and ship
    # it to the classifier on every run. Both tiers land here, so the guard does.
    if identifiers := [c for c in mapping.desc_cols if is_sensitive_column(c)]:
        raise ParseError(f"Refusing to use identifier column(s) as the description: {identifiers}")

    idx = {h: i for i, h in enumerate(headers)}
    posted = {v.lower() for v in mapping.posted_values}

    results: list[ExtractedTxn] = []
    skipped_unposted = 0
    for row in data_rows:
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        if mapping.status_col:
            status = str(_cell(row, idx[mapping.status_col]) or "").strip().lower()
            if status and status not in posted:
                skipped_unposted += 1
                continue
        try:
            txn_date = _coerce_date(_cell(row, idx[mapping.date_col]))
            description = " ".join(
                part
                for col in mapping.desc_cols
                if (part := str(_cell(row, idx[col]) or "").strip())
            )
            amount = _row_amount(mapping, row, idx)
        except (IndexError, ParseError):
            # Skip rows we can't decode — totals/footers/blank lines.
            continue
        if not description or amount is None:
            continue
        results.append(ExtractedTxn(txn_date=txn_date, description=description, amount=amount))

    if skipped_unposted:
        logger.info("Skipped %d non-posted row(s) via %r", skipped_unposted, mapping.status_col)
    if not results:
        raise ParseError("Mapper produced zero transactions")
    return results


def _headers_and_rows(rows: list[dict[str, str]]) -> tuple[list[str], list[list[Any]]]:
    headers = list(rows[0].keys())
    return headers, [[r.get(h) for h in headers] for r in rows]


def _xlsx_headers_and_rows(rows: list[list[Any]]) -> tuple[list[str], list[list[Any]]]:
    headers = [str(h) if h is not None else "" for h in rows[0]]
    return headers, list(rows[1:])


def _missing_columns_error(headers: Sequence[str]) -> ParseError:
    return ParseError(
        f"Could not resolve the transaction columns. Headers: {list(headers)}. "
        f"Need a date column, a description column, and either an amount column "
        f"or a debit/credit pair."
    )


def csv_to_transactions(rows: list[dict[str, str]]) -> list[ExtractedTxn]:
    if not rows:
        raise ParseError("No CSV rows to map")
    headers, data_rows = _headers_and_rows(rows)
    mapping = _resolve_columns(headers)
    if mapping is None:
        raise _missing_columns_error(headers)
    return _apply_mapping(mapping, headers, data_rows)


def xlsx_to_transactions(rows: list[list[Any]]) -> list[ExtractedTxn]:
    if not rows:
        raise ParseError("No XLSX rows to map")
    headers, data_rows = _xlsx_headers_and_rows(rows)
    mapping = _resolve_columns(headers)
    if mapping is None:
        raise _missing_columns_error(headers)
    return _apply_mapping(mapping, headers, data_rows)


# ── tier 2: agent-resolved schema ───────────────────────────────────────────

SAMPLE_ROWS = 5


def _build_schema_prompt(headers: Sequence[str], data_rows: Sequence[Sequence[Any]]) -> str:
    """Header row plus a few redacted sample rows — the whole of what the agent sees.

    `redact_columns` masks identifier columns by header name first, then
    `scrub_text` sweeps the rest, so nothing here depends on a digit-run rule
    catching a short account number.

    `mask_bare_identifiers` is on because this path only runs when the headers were
    unrecognizable — "Numero de Cuenta" is an account column no alias list knows, so
    here the value's shape is the only signal left.

    No `keep_terms`: those exist so the orchestrator can still match an institution
    name to a source account. This agent only names columns, so nothing it needs to
    do is worth letting an institution or product name through unredacted.
    """
    samples = list(data_rows[:SAMPLE_ROWS])
    if settings.scrub_before_llm:
        samples, column_report = redact_columns(headers, samples, mask_bare_identifiers=True)
        rendered = "\n".join(" | ".join(cells) for cells in samples)
        rendered, text_report = scrub_text(rendered)
        logger.info(
            "Scrubbed schema-mapper samples: %s %s",
            column_report.summary(),
            text_report.summary(),
        )
    else:
        logger.warning("SCRUB_BEFORE_LLM is off — sending raw sample rows to the LLM")
        rendered = "\n".join(
            " | ".join("" if c is None else str(c) for c in row) for row in samples
        )

    return f"Header row:\n{' | '.join(headers)}\n\nSample rows:\n{rendered}"


def _mapping_from_agent(resolved: ResolvedColumns, headers: Sequence[str]) -> ColumnMapping:
    """Validate the agent's answer against the real header row before trusting it.

    Every name has to be a header that actually exists. An invented column would
    otherwise surface as a confusing IndexError deep in row decoding, and a
    plausible-but-wrong one could silently map the wrong number.
    """
    known = {_norm(h): h for h in headers}

    def resolve(name: str | None, field: str) -> str | None:
        if name is None or not str(name).strip():
            return None
        actual = known.get(_norm(name))
        if actual is None:
            raise ParseError(
                f"Schema mapper returned {field}={name!r}, which is not a column in "
                f"this file. Headers: {list(headers)}"
            )
        return actual

    desc_cols = tuple(
        col for raw in resolved.description_columns if (col := resolve(raw, "description_column"))
    )
    date_col = resolve(resolved.date_column, "date_column")
    if not date_col or not desc_cols:
        raise ParseError("Schema mapper did not return both a date and a description column")

    amount_col = resolve(resolved.amount_column, "amount_column")
    debit_col = resolve(resolved.debit_column, "debit_column")
    credit_col = resolve(resolved.credit_column, "credit_column")
    if not amount_col and not (debit_col and credit_col):
        raise ParseError("Schema mapper returned neither an amount column nor a debit/credit pair")

    return ColumnMapping(
        date_col=date_col,
        desc_cols=desc_cols,
        amount_col=amount_col,
        debit_col=None if amount_col else debit_col,
        credit_col=None if amount_col else credit_col,
        debit_is_negative=resolved.debit_is_negative,
        status_col=resolve(resolved.status_column, "status_column"),
        posted_values=tuple(v.lower() for v in resolved.posted_values) or POSTED_VALUES,
    )


async def _to_transactions_async(
    headers: Sequence[str], data_rows: Sequence[Sequence[Any]]
) -> tuple[list[ExtractedTxn], bool]:
    """Resolve the layout, falling back to the agent. Returns (txns, used_llm)."""
    mapping = _resolve_columns(headers)
    if mapping is not None:
        return _apply_mapping(mapping, headers, data_rows), False

    logger.info("No deterministic column mapping for %s — asking the schema mapper", list(headers))
    resolved = await run_schema_mapper(_build_schema_prompt(headers, data_rows))
    mapping = _mapping_from_agent(resolved, headers)
    logger.info("Schema mapper resolved %s (%s)", mapping, resolved.reason)
    return _apply_mapping(mapping, headers, data_rows), True


async def csv_to_transactions_async(rows: list[dict[str, str]]) -> tuple[list[ExtractedTxn], bool]:
    if not rows:
        raise ParseError("No CSV rows to map")
    return await _to_transactions_async(*_headers_and_rows(rows))


async def xlsx_to_transactions_async(rows: list[list[Any]]) -> tuple[list[ExtractedTxn], bool]:
    if not rows:
        raise ParseError("No XLSX rows to map")
    return await _to_transactions_async(*_xlsx_headers_and_rows(rows))
