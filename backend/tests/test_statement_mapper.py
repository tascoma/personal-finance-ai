"""Unit tests for the deterministic CSV/XLSX → ExtractedTxn mapper.

These are pure-function tests — no DB or fixtures needed.
"""

from datetime import date, datetime

import pytest

from app.services.file_readers import ParseError
from app.services.statement_mapper import (
    csv_to_transactions,
    xlsx_to_transactions,
)


def test_csv_happy_path_bank_ozk_shape():
    rows = [
        {"Date": "2026-01-05", "Description": "Paycheck", "ChkRef": "", "Amount": "$2,569.00 ", "Balance": "5000"},
        {"Date": "2026-01-06", "Description": "Coffee", "ChkRef": "", "Amount": "($25.00)", "Balance": "4975"},
    ]
    txns = csv_to_transactions(rows)
    assert len(txns) == 2
    assert txns[0].txn_date == date(2026, 1, 5)
    assert txns[0].description == "Paycheck"
    assert txns[0].amount == pytest.approx(2569.00)
    assert txns[1].amount == pytest.approx(-25.00)


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
    assert txns[0].amount == pytest.approx(-54.20)
    assert txns[1].amount == pytest.approx(12.00)


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
    assert txns[0].amount == pytest.approx(10.0)


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
        ("$1,234.56", 1234.56),
        ("(12.34)", -12.34),
        ("($1,000.00)", -1000.00),
        ("  $42 ", 42.0),
        ("-5.5", -5.5),
    ],
)
def test_amount_format_edge_cases(raw, expected):
    rows = [{"Date": "2026-03-01", "Description": "X", "Amount": raw}]
    assert csv_to_transactions(rows)[0].amount == pytest.approx(expected)


def test_empty_rows_raise():
    with pytest.raises(ParseError, match="No CSV rows"):
        csv_to_transactions([])
    with pytest.raises(ParseError, match="No XLSX rows"):
        xlsx_to_transactions([])


def test_missing_required_columns_raise():
    rows = [{"Date": "2026-03-01", "Balance": "100"}]  # no description, no amount
    with pytest.raises(ParseError, match="Missing required columns"):
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
