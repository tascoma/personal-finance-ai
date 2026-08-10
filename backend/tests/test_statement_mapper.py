"""Unit tests for the deterministic CSV/XLSX → ExtractedTxn mapper.

These are pure-function tests — no DB or fixtures needed.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.config import settings
from app.services import statement_mapper
from app.services.file_readers import ParseError
from app.services.statement_mapper import (
    _resolve_columns,
    csv_to_transactions,
    xlsx_to_transactions,
)


def new_format_row(**overrides):
    """One row of the bank's current export: Debit/Credit split, no signed Amount."""
    row = {
        "Account Number": "2122902212",
        "Post Date": "7/30/2026",
        "Check": "",
        "Description": "WAL-MART ASSOCS. PAYROLL XXXXXX3311",
        "Debit": "",
        "Credit": "2541.90",
        "Status": "Posted",
        "Balance": "",
    }
    return {**row, **overrides}


def test_csv_happy_path_bank_ozk_shape():
    rows = [
        {"Date": "2026-01-05", "Description": "Paycheck", "ChkRef": "", "Amount": "$2,569.00 ", "Balance": "5000"},
        {"Date": "2026-01-06", "Description": "Coffee", "ChkRef": "", "Amount": "($25.00)", "Balance": "4975"},
    ]
    txns = csv_to_transactions(rows)
    assert len(txns) == 2
    assert txns[0].txn_date == date(2026, 1, 5)
    assert txns[0].description == "Paycheck"
    assert txns[0].amount == Decimal("2569.00")
    assert txns[1].amount == Decimal("-25.00")


def test_csv_happy_path_new_bank_ozk_shape_with_split_debit_credit():
    rows = [
        new_format_row(),
        new_format_row(
            **{
                "Post Date": "7/28/2026",
                "Description": "XX3178 MT DDA DEBIT VENMO",
                "Debit": "160.00",
                "Credit": "",
            }
        ),
    ]
    txns = csv_to_transactions(rows)
    assert len(txns) == 2
    # Credit is money in, debit is money out — the sign convention the statement
    # extractor prompt and the journal builder both already assume.
    assert txns[0].amount == Decimal("2541.90")
    assert txns[1].amount == Decimal("-160.00")
    assert txns[0].txn_date == date(2026, 7, 30)


def test_split_columns_with_both_sides_populated_net_out():
    txns = csv_to_transactions([new_format_row(Debit="40.00", Credit="100.00")])
    assert txns[0].amount == Decimal("60.00")


def test_split_columns_ignore_a_sign_the_bank_already_applied():
    # A "-160.00" inside a column named Debit must not be negated twice.
    txns = csv_to_transactions([new_format_row(Debit="-160.00", Credit="")])
    assert txns[0].amount == Decimal("-160.00")


def test_rows_with_neither_debit_nor_credit_are_skipped():
    rows = [new_format_row(), new_format_row(Debit="", Credit="", Description="MEMO ONLY")]
    txns = csv_to_transactions(rows)
    assert [t.description for t in txns] == ["WAL-MART ASSOCS. PAYROLL XXXXXX3311"]


@pytest.mark.parametrize("status", ["Pending", "Authorized", "Hold"])
def test_non_posted_rows_are_skipped(status):
    # The bank may still reverse these; posting one double-counts when the settled
    # row arrives.
    rows = [new_format_row(), new_format_row(Status=status, Description="PENDING COFFEE")]
    txns = csv_to_transactions(rows)
    assert [t.description for t in txns] == ["WAL-MART ASSOCS. PAYROLL XXXXXX3311"]


@pytest.mark.parametrize("status", ["Posted", "Cleared", "Settled", "posted", ""])
def test_posted_and_blank_statuses_are_kept(status):
    assert len(csv_to_transactions([new_format_row(Status=status)])) == 1


@pytest.mark.parametrize(
    "header", ["Post Date", "post_date", "POST DATE", "Post-Date", "Posting Date", "Trans Date"]
)
def test_header_matching_ignores_case_and_separators(header):
    mapping = _resolve_columns([header, "Description", "Amount"])
    assert mapping is not None and mapping.date_col == header


@pytest.mark.parametrize(
    "debit,credit",
    [("Debit", "Credit"), ("Withdrawal", "Deposit"), ("Money Out", "Money In"), ("Charges", "Payments")],
)
def test_debit_credit_pairs_are_recognized_by_alias(debit, credit):
    mapping = _resolve_columns(["Date", "Description", debit, credit])
    assert mapping is not None
    assert (mapping.debit_col, mapping.credit_col) == (debit, credit)
    assert mapping.amount_col is None


def test_a_signed_amount_column_wins_over_a_debit_credit_pair():
    mapping = _resolve_columns(["Date", "Description", "Amount", "Debit", "Credit"])
    assert mapping.amount_col == "Amount"
    assert mapping.debit_col is None and mapping.credit_col is None


@pytest.mark.parametrize(
    "headers",
    [
        ["Col1", "Col2", "Col3"],
        ["Fecha", "Concepto", "Importe"],
        ["Date", "Description"],          # no amount and no debit/credit pair
        ["Date", "Amount"],               # no description
        ["Description", "Amount"],        # no date
        ["Date", "Description", "Debit"],  # a half pair is not a pair
    ],
)
def test_unresolvable_headers_return_none_so_the_agent_can_try(headers):
    assert _resolve_columns(headers) is None


def test_identifier_column_is_refused_as_the_description():
    # `RawTransaction.description` is stored verbatim, so mapping an identifier
    # column onto it would persist an account number and ship it to the classifier.
    from app.services.statement_mapper import ColumnMapping, _apply_mapping

    mapping = ColumnMapping(
        date_col="Post Date", desc_cols=("Account Number",), amount_col="Credit"
    )
    with pytest.raises(ParseError, match="Refusing to use identifier column"):
        _apply_mapping(mapping, list(new_format_row().keys()), [list(new_format_row().values())])


# ── tier 2: the schema-mapper agent ─────────────────────────────────────────


FOREIGN_ROWS = [
    {"Fecha": "2026-03-01", "Concepto": "SUPERMERCADO", "Cargo": "54.20", "Abono": ""},
    {"Fecha": "2026-03-02", "Concepto": "NOMINA", "Cargo": "", "Abono": "1200.00"},
]


def stub_schema_mapper(monkeypatch, **fields):
    """Patch the agent to return a fixed mapping, and capture the prompt it saw."""
    from app.agents.statement import ResolvedColumns

    seen = {}

    async def fake(prompt: str) -> ResolvedColumns:
        seen["prompt"] = prompt
        return ResolvedColumns(**fields)

    monkeypatch.setattr(statement_mapper, "run_schema_mapper", fake)
    return seen


async def test_known_format_never_calls_the_agent(monkeypatch):
    async def explode(prompt):  # pragma: no cover - must not run
        raise AssertionError("the deterministic tier should have resolved this")

    monkeypatch.setattr(statement_mapper, "run_schema_mapper", explode)
    txns, used_llm = await statement_mapper.csv_to_transactions_async([new_format_row()])
    assert used_llm is False
    assert txns[0].amount == Decimal("2541.90")


async def test_agent_resolves_an_unknown_layout(monkeypatch):
    stub_schema_mapper(
        monkeypatch,
        date_column="Fecha",
        description_columns=["Concepto"],
        debit_column="Cargo",
        credit_column="Abono",
        reason="Spanish-language export",
    )
    txns, used_llm = await statement_mapper.csv_to_transactions_async(FOREIGN_ROWS)

    assert used_llm is True
    assert [t.description for t in txns] == ["SUPERMERCADO", "NOMINA"]
    assert txns[0].amount == Decimal("-54.20")
    assert txns[1].amount == Decimal("1200.00")


async def test_agent_prompt_carries_headers_and_redacted_samples(monkeypatch):
    seen = stub_schema_mapper(
        monkeypatch,
        date_column="Fecha",
        description_columns=["Concepto"],
        debit_column="Cargo",
        credit_column="Abono",
    )
    rows = [{**FOREIGN_ROWS[0], "Numero de Cuenta": "21229022"}]
    rows[0] = {"Numero de Cuenta": "21229022", **FOREIGN_ROWS[0]}
    await statement_mapper.csv_to_transactions_async(rows)

    prompt = seen["prompt"]
    assert "Fecha" in prompt and "Concepto" in prompt  # headers survive; it maps them
    assert "SUPERMERCADO" in prompt                    # sample values survive
    assert "21229022" not in prompt                    # ...but identifiers do not


async def test_agent_column_that_is_not_in_the_file_is_rejected(monkeypatch):
    # A hallucinated column name must fail loudly rather than mis-map a number.
    stub_schema_mapper(
        monkeypatch,
        date_column="Fecha",
        description_columns=["Descripcion"],  # not a header in FOREIGN_ROWS
        debit_column="Cargo",
        credit_column="Abono",
    )
    with pytest.raises(ParseError, match="not a column in this file"):
        await statement_mapper.csv_to_transactions_async(FOREIGN_ROWS)


async def test_agent_must_return_an_amount_or_a_debit_credit_pair(monkeypatch):
    stub_schema_mapper(
        monkeypatch, date_column="Fecha", description_columns=["Concepto"], debit_column="Cargo"
    )
    with pytest.raises(ParseError, match="neither an amount column nor a debit/credit pair"):
        await statement_mapper.csv_to_transactions_async(FOREIGN_ROWS)


async def test_agent_cannot_map_an_identifier_column_onto_the_description(monkeypatch):
    stub_schema_mapper(
        monkeypatch,
        date_column="Fecha",
        description_columns=["Reference"],
        debit_column="Cargo",
        credit_column="Abono",
    )
    rows = [{**r, "Reference": "998877665544"} for r in FOREIGN_ROWS]
    with pytest.raises(ParseError, match="Refusing to use identifier column"):
        await statement_mapper.csv_to_transactions_async(rows)


def test_xlsx_happy_path_numeric_amounts_and_datetime_dates():
    rows = [
        ["Date", "Transaction", "Name", "Memo", "Amount"],
        [datetime(2026, 2, 1, 12, 0), "Grocery", "Store", "", -54.20],
        [datetime(2026, 2, 2, 9, 0), "Refund", "Store", "", 12.00],
    ]
    txns = xlsx_to_transactions(rows)
    assert len(txns) == 2
    assert txns[0].txn_date == date(2026, 2, 1)
    # "Name" is in DESC_ALIASES and wins over the non-aliased "Transaction" column.
    assert txns[0].description == "Store"
    assert txns[0].amount == Decimal("-54.20")
    assert txns[1].amount == Decimal("12.00")


@pytest.mark.parametrize("date_header", ["Date", "Transaction Date", "Posted Date", "Post Date"])
def test_date_column_aliases(date_header):
    rows = [{date_header: "2026-03-01", "Description": "X", "Amount": "10"}]
    txns = csv_to_transactions(rows)
    assert txns[0].txn_date == date(2026, 3, 1)


@pytest.mark.parametrize("desc_header", ["Description", "Name", "Memo", "Payee", "Merchant"])
def test_description_column_aliases(desc_header):
    rows = [{"Date": "2026-03-01", desc_header: "Acme", "Amount": "10"}]
    txns = csv_to_transactions(rows)
    assert txns[0].description == "Acme"


@pytest.mark.parametrize("amount_header", ["Amount", "Transaction Amount"])
def test_amount_column_aliases(amount_header):
    rows = [{"Date": "2026-03-01", "Description": "X", amount_header: "10"}]
    txns = csv_to_transactions(rows)
    assert txns[0].amount == Decimal("10.0")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-03-01", date(2026, 3, 1)),
        ("03/01/2026", date(2026, 3, 1)),
        ("03/01/26", date(2026, 3, 1)),
        ("3/1/26", date(2026, 3, 1)),
        ("3/1/2026", date(2026, 3, 1)),
        ("03-01-2026", date(2026, 3, 1)),
    ],
)
def test_all_supported_date_formats(raw, expected):
    rows = [{"Date": raw, "Description": "X", "Amount": "1"}]
    assert csv_to_transactions(rows)[0].txn_date == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,234.56", Decimal("1234.56")),
        ("(12.34)", Decimal("-12.34")),
        ("($1,000.00)", Decimal("-1000.00")),
        ("  $42 ", Decimal("42")),
        ("-5.5", Decimal("-5.5")),
    ],
)
def test_amount_format_edge_cases(raw, expected):
    rows = [{"Date": "2026-03-01", "Description": "X", "Amount": raw}]
    assert csv_to_transactions(rows)[0].amount == expected


def test_empty_rows_raise():
    with pytest.raises(ParseError, match="No CSV rows"):
        csv_to_transactions([])
    with pytest.raises(ParseError, match="No XLSX rows"):
        xlsx_to_transactions([])


def test_missing_required_columns_raise():
    rows = [{"Date": "2026-03-01", "Balance": "100"}]  # no description, no amount
    with pytest.raises(ParseError, match="Could not resolve the transaction columns"):
        csv_to_transactions(rows)


def test_blank_and_footer_rows_skipped():
    rows = [
        ["Date", "Description", "Amount"],
        ["2026-04-01", "Real txn", 10.0],
        ["", "", ""],  # blank row
        ["Total", "", "999"],  # footer with unparseable date
    ]
    txns = xlsx_to_transactions(rows)
    assert len(txns) == 1
    assert txns[0].description == "Real txn"


def test_all_undecodable_rows_raise():
    rows = [
        ["Date", "Description", "Amount"],
        ["not-a-date", "X", "abc"],
    ]
    with pytest.raises(ParseError, match="zero transactions"):
        xlsx_to_transactions(rows)


def test_rows_with_blank_description_skipped():
    rows = [{"Date": "2026-04-01", "Description": "   ", "Amount": "10"}]
    with pytest.raises(ParseError, match="zero transactions"):
        csv_to_transactions(rows)


# ── ragged rows ──────────────────────────────────────────────────────────────


def test_ragged_rows_do_not_fail_the_document():
    # openpyxl drops trailing empty cells, so a row whose last columns are blank
    # arrives shorter than the header. One short row must not kill the parse.
    rows = [
        ["Post Date", "Description", "Debit", "Credit", "Status"],
        ["7/30/2026", "PAYROLL", "", "2541.90", "Posted"],
        ["7/29/2026", "SHORT ROW"],
        ["7/28/2026", "COFFEE", "4.50", "", "Posted"],
    ]
    txns = xlsx_to_transactions(rows)
    # The short row carries no amount, so it is skipped rather than posted at zero.
    assert [t.description for t in txns] == ["PAYROLL", "COFFEE"]
    assert txns[1].amount == Decimal("-4.50")


def test_ragged_row_missing_only_its_status_is_still_posted():
    rows = [
        ["Post Date", "Description", "Debit", "Credit", "Status"],
        ["7/30/2026", "PAYROLL", "", "2541.90"],
    ]
    assert len(xlsx_to_transactions(rows)) == 1


# ── xlsx parity with the csv path ────────────────────────────────────────────


def test_xlsx_supports_split_debit_credit_and_status():
    rows = [
        ["Account Number", "Post Date", "Description", "Debit", "Credit", "Status"],
        ["2122902212", datetime(2026, 7, 30), "PAYROLL", None, 2541.90, "Posted"],
        ["2122902212", datetime(2026, 7, 28), "VENMO", 160.00, None, "Posted"],
        ["2122902212", datetime(2026, 7, 27), "PENDING COFFEE", 4.50, None, "Pending"],
    ]
    txns = xlsx_to_transactions(rows)
    assert [t.description for t in txns] == ["PAYROLL", "VENMO"]
    assert txns[0].amount == Decimal("2541.90")
    assert txns[1].amount == Decimal("-160.00")


async def test_xlsx_falls_back_to_the_agent_too(monkeypatch):
    stub_schema_mapper(
        monkeypatch,
        date_column="Fecha",
        description_columns=["Concepto"],
        debit_column="Cargo",
        credit_column="Abono",
    )
    rows = [["Fecha", "Concepto", "Cargo", "Abono"], ["2026-03-01", "SUPERMERCADO", 54.20, None]]
    txns, used_llm = await statement_mapper.xlsx_to_transactions_async(rows)
    assert used_llm is True
    assert txns[0].amount == Decimal("-54.20")


async def test_schema_prompt_is_raw_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(settings, "scrub_before_llm", False)
    seen = stub_schema_mapper(
        monkeypatch,
        date_column="Fecha",
        description_columns=["Concepto"],
        debit_column="Cargo",
        credit_column="Abono",
    )
    rows = [{"Numero de Cuenta": "21229022", **FOREIGN_ROWS[0]}]
    await statement_mapper.csv_to_transactions_async(rows)
    assert "21229022" in seen["prompt"]
