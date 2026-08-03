from datetime import date

from pydantic import BaseModel

from app.agents._base import build_agent, run_agent

SYSTEM_PROMPT = (
    "You extract transaction rows from a bank or credit card statement. "
    "Return one row per posted transaction. Skip running balances, headers, "
    "summaries, and pending transactions. Sign amounts: deposits/credits are "
    "positive, withdrawals/charges are negative. Dates use the statement "
    "period's year if the row only shows MM/DD."
)


class ExtractedTxn(BaseModel):
    txn_date: date
    description: str
    amount: float  # signed: positive = money in, negative = money out


class ExtractedStatement(BaseModel):
    transactions: list[ExtractedTxn]


agent = build_agent(ExtractedStatement, SYSTEM_PROMPT)


async def run_statement_extractor(text: str) -> ExtractedStatement:
    return await run_agent(agent, "statement extractor", text)


# ── schema mapper ───────────────────────────────────────────────────────────
#
# The fallback tier for CSV/XLSX, used only when `app.services.statement_mapper`
# cannot resolve a header row from its alias lists. It names columns and nothing
# else — every date and amount is still decoded deterministically — so the worst
# a wrong answer can do is fail to parse, never quietly change a number.

SCHEMA_PROMPT = (
    "You map the columns of a bank or credit card export to a transaction schema. "
    "You are given the header row and a few sample data rows; identifiers in them "
    "are already redacted. Return the column NAMES exactly as they appear in the "
    "header — never invent a name, never return a value from a data row.\n"
    "Amount: if one column holds a signed amount, set amount_column and leave the "
    "debit/credit pair null. If money out and money in are in separate columns, set "
    "debit_column and credit_column and leave amount_column null. Set "
    "debit_is_negative true when the debit column is money leaving the account "
    "(the normal case).\n"
    "Description: the human-readable payee or memo. Prefer one good column; list "
    "several only when the description is genuinely split across them. Never choose "
    "a column of account numbers, card numbers, check numbers, or reference codes.\n"
    "Status: only if a column marks rows posted vs pending. Put the values that mean "
    "'this row is final' in posted_values, lowercased."
)


class ResolvedColumns(BaseModel):
    date_column: str
    description_columns: list[str]
    amount_column: str | None = None
    debit_column: str | None = None
    credit_column: str | None = None
    debit_is_negative: bool = True
    status_column: str | None = None
    posted_values: list[str] = []
    reason: str = ""


schema_agent = build_agent(ResolvedColumns, SCHEMA_PROMPT)


async def run_schema_mapper(prompt: str) -> ResolvedColumns:
    return await run_agent(schema_agent, "schema mapper", prompt)
