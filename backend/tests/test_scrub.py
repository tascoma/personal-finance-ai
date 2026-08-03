"""Unit tests for the deterministic PII/PCI scrubber.

These are pure-function tests — no DB or fixtures needed. `pii_identity_terms`
is a settings value, so the few tests that exercise it patch `settings` directly.
"""

import pytest

from app.core.config import settings
from app.services.scrub import (
    is_sensitive_column,
    normalize_header,
    redact_columns,
    scrub_description,
    scrub_text,
)


def scrubbed(text: str, **kwargs) -> str:
    """Drop the report — most cases only care about the text."""
    return scrub_text(text, **kwargs)[0]


# ── card numbers (PCI) ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pan",
    [
        "4111111111111111",       # Visa test PAN
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
        "5555555555554444",       # Mastercard test PAN
        "378282246310005",         # Amex test PAN, 15 digits
    ],
)
def test_luhn_valid_pans_are_masked_to_last4(pan):
    assert scrubbed(f"PAYMENT {pan} POSTED") == "PAYMENT [CARD ••" + pan[-4:] + "] POSTED"


def test_non_luhn_long_run_is_not_labelled_as_a_card():
    # A 16-digit ACH trace number. Luhn is what separates it from a real PAN —
    # length alone would guess. It still gets masked, just not as a card.
    out = scrubbed("REF 1234567890123456 posted")
    assert "[CARD" not in out
    assert out == "REF [NUM ••3456] posted"


# ── labelled identifiers ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Account Number 1234567890", "Account Number [ACCT ••7890]"),
        # pdfplumber collapses the label into one token on real statements.
        ("AccountNumber 1234567890", "AccountNumber [ACCT ••7890]"),
        ("Emp #: 123456789", "Emp #: [ACCT ••6789]"),
        ("Acct No. 55512345", "Acct No. [ACCT ••2345]"),
        ("Loan number 998877665", "Loan number [ACCT ••7665]"),
        ("Member ID 4455667788", "Member ID [ACCT ••7788]"),
    ],
)
def test_labelled_identifiers_keep_their_label_and_last4(text, expected):
    assert scrubbed(text) == expected


def test_short_identifier_values_are_left_alone():
    # Fewer than 4 digits carries no identifying weight and may be a real datum.
    assert scrubbed("Account 12") == "Account 12"


def test_already_masked_deposit_reference_survives_intact():
    # Payroll providers print the net-pay destination pre-masked, and the
    # orchestrator matches a paystub to its deposit account on exactly this.
    assert scrubbed("Direct Deposit XXXXXX1234 net pay") == "Direct Deposit XXXXXX1234 net pay"


# ── generic long digit runs ─────────────────────────────────────────────────


def test_mail_routing_barcode_is_masked():
    assert scrubbed("1-234-56789-1234567-123-456-789-012-345") == "[NUM ••2345]"


def test_csv_trace_number_is_masked():
    assert scrub_description("SQ *COFFEE 8829384719283 0429") == "SQ *COFFEE [NUM ••9283] 0429"


def test_trailing_comma_does_not_shield_a_long_run():
    # The digest peek renders as "Description=REF 8829384719283, ChkRef=".
    assert scrub_description("REF 8829384719283, next") == "REF [NUM ••9283], next"


@pytest.mark.parametrize(
    "text,expected",
    [
        # A leading dash must not hide an identifier.
        ("ACCT-1234567890", "ACCT-[ACCT ••7890]"),
        ("Card No-4111111111111111", "Card No-[CARD ••1111]"),
    ],
)
def test_dash_separated_identifiers_are_masked(text, expected):
    assert scrubbed(text) == expected


def test_long_amount_without_thousands_separators_is_not_masked():
    # Ten integer digits followed by cents is money, not an identifier.
    assert scrubbed("Balance 1234567890.55") == "Balance 1234567890.55"


# ── things that must never be touched ───────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "Total pay $1,234.56",
        "Gross 12,345.00 Net 9,876.54",
        "45.00",
        "Statement Date 04/30/2026",
        "Posted 2026-04-30",
        "Period 04-30-2026 to 05-31-2026",
        "INS MED U PT",
        "REGULAR EARNING",
        "ROTH 401K",
        "Account 12",
    ],
)
def test_amounts_dates_and_payroll_labels_pass_through_unchanged(text):
    assert scrubbed(text) == text


# ── identity terms ──────────────────────────────────────────────────────────


def test_identity_terms_are_matched_literally_and_case_insensitively(monkeypatch):
    monkeypatch.setattr(settings, "pii_identity_terms", "Anthony Scoma")
    assert scrubbed("Pay to ANTHONY SCOMA only") == "Pay to [NAME] only"


def test_longest_identity_term_wins(monkeypatch):
    # "Scoma" alone would leave "Anthony [NAME]" behind.
    monkeypatch.setattr(settings, "pii_identity_terms", "Scoma,Anthony Scoma")
    assert scrubbed("Anthony Scoma") == "[NAME]"


def test_identity_terms_beat_keep_terms(monkeypatch):
    # An account the user named after themselves: privacy wins, and they can
    # rename the account if source-account matching suffers.
    monkeypatch.setattr(settings, "pii_identity_terms", "Scoma")
    assert scrubbed("Scoma Family Checking", keep_terms=["Scoma Family Checking"]) == (
        "[NAME] Family Checking"
    )


def test_empty_identity_terms_setting_is_a_no_op(monkeypatch):
    monkeypatch.setattr(settings, "pii_identity_terms", "")
    assert scrubbed("Anthony Scoma") == "Anthony Scoma"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        ("  ", []),
        ("A", ["A"]),
        ("A,B", ["A", "B"]),
        (" A , , B ", ["A", "B"]),
    ],
)
def test_identity_term_list_parsing(monkeypatch, raw, expected):
    monkeypatch.setattr(settings, "pii_identity_terms", raw)
    assert settings.pii_identity_term_list == expected


# ── keep_terms ──────────────────────────────────────────────────────────────


def test_keep_terms_and_last4_both_survive():
    # Both halves of the orchestrator's source-account match.
    out = scrubbed(
        "Chase Sapphire Reserve ending 1234", keep_terms=["Chase Sapphire Reserve"]
    )
    assert "Chase Sapphire Reserve" in out
    assert "1234" in out


def test_keep_term_is_protected_from_the_address_rule():
    out = scrubbed("500 Terrace Bank Checking deposit", keep_terms=["500 Terrace Bank Checking"])
    assert out == "500 Terrace Bank Checking deposit"


# ── contact details and addresses ───────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("SSN 123-45-6789", "SSN [SSN]"),
        ("reach us at a.b+c@example.com", "reach us at [EMAIL]"),
        ("Call 555-123-4567", "Call [PHONE]"),
        ("Call (555) 123-4567", "Call [PHONE]"),
        ("Call +1 555.123.4567", "Call [PHONE]"),
        ("see www.bank.example", "see [URL]"),
        ("see https://bank.example/x?y=1", "see [URL]"),
        ("P.O. Box 12345", "[ADDRESS]"),
        ("PO BOX 999", "[ADDRESS]"),
        ("1234 N MAIN ST APT#305", "[ADDRESS]"),
        ("77 Oak Avenue Suite 200", "[ADDRESS]"),
        ("SPRINGFIELD, IL 62704", "[CITY, ST ZIP]"),
        ("Springfield IL 62704-1234", "[CITY, ST ZIP]"),
    ],
)
def test_contact_and_address_rules(text, expected):
    assert scrubbed(text) == expected


@pytest.mark.parametrize(
    "unit",
    ["C#211", "#211", "APT 4B", "Apt#305", "Ste B", "Unit 12", "Bldg 2"],
)
def test_unit_numbers_are_redacted_with_the_street(unit):
    # "C#211" is a real apartment number off a paystub and carries no APT keyword.
    out = scrubbed(f"123 MAIN ST {unit} BENTONVILLE, AR 72712")
    assert out == "[ADDRESS] [CITY, ST ZIP]"


@pytest.mark.parametrize(
    "text",
    [
        # The street suffix must be a whole token, not the tail of a word:
        # "100 Interest" is <100> <Intere> <st> to a careless pattern.
        "Total 100 Interest",
        "Escrow 250 Adjustment",
        "Payment 30 Days",
    ],
)
def test_street_suffix_does_not_match_the_tail_of_an_ordinary_word(text):
    assert scrubbed(text) == text


@pytest.mark.parametrize(
    "text,expected",
    [
        # Some servicers' PDFs extract with every space stripped.
        ("PropertyAddress: 6203S37THST", "PropertyAddress: [ADDRESS]"),
        ("ROGERSAR72758", "[CITY, ST ZIP]"),
        ("Dallas,TX75379-9063", "[CITY, ST ZIP]"),
    ],
)
def test_space_collapsed_addresses_are_redacted(text, expected):
    assert scrubbed(text) == expected


def test_glued_identifier_is_not_mistaken_for_an_account_number():
    # "LoanNumber:6203S37THST" is the property address glued to a label. Masking
    # the leading digits would mangle it and report a bogus last-4.
    out = scrubbed("LoanNumber:6203S37THST")
    assert "[ACCT" not in out
    assert "S37THST" not in out


def test_identity_terms_match_across_stripped_whitespace(monkeypatch):
    # A configured "Michael Anthony" has to match a PDF that extracted as
    # "MICHAELANTHONY", so whitespace inside a term is treated as optional.
    monkeypatch.setattr(settings, "pii_identity_terms", "Michael Anthony")
    assert scrubbed("MICHAELANTHONYSCOMA") == "[NAME]SCOMA"


def test_adjacent_name_placeholders_collapse(monkeypatch):
    monkeypatch.setattr(settings, "pii_identity_terms", "Michael Anthony,Scoma")
    assert scrubbed("MICHAELANTHONYSCOMA") == "[NAME]"
    assert scrubbed("Michael Anthony Scoma") == "[NAME]"


def test_unit_number_is_redacted_without_a_trailing_city():
    assert scrubbed("123 MAIN ST C#211") == "[ADDRESS]"


def test_address_gap_collapse_will_not_swallow_money():
    # The gap rule is bounded: a `$` between the fragments means it is not a unit.
    out = scrubbed("123 MAIN ST $1,234.56 BENTONVILLE, AR 72712")
    assert "$1,234.56" in out


def test_address_rules_never_span_a_line_break():
    # A match crossing a newline welds two unrelated lines together and takes the
    # content between them with it.
    text = "Deposit Date: 05/21/2026\n123 MAIN ST BENTONVILLE, AR 72712\nNet Pay $2,534.32"
    out = scrubbed(text)
    assert out.count("\n") == 2
    assert out.splitlines()[0] == "Deposit Date: 05/21/2026"
    assert out.splitlines()[2] == "Net Pay $2,534.32"


def test_street_rule_does_not_eat_a_date_that_precedes_an_address():
    # Real paystub layout: the mailing address follows the deposit date on the
    # same line, so a naive street rule matches from the year and destroys it.
    # `pay_date` is the extractor's whole job — the date has to survive.
    out = scrubbed("Deposit Date: 05/21/2026 123 MAIN ST C#211 BENTONVILLE, AR 72712")
    assert "05/21/2026" in out
    assert "123 MAIN ST" not in out
    assert "BENTONVILLE" not in out


def test_scrub_description_leaves_merchant_names_that_look_like_addresses():
    # "1200 MARKET ST DELI" is a store name, not a mailing address. The
    # classifier needs it, so scrub_description skips the address rules — while
    # the same string inside a document body is treated as an address.
    assert scrub_description("1200 MARKET ST DELI") == "1200 MARKET ST DELI"
    assert scrubbed("1200 MARKET ST DELI") == "[ADDRESS] DELI"


# ── report ──────────────────────────────────────────────────────────────────


def test_report_counts_by_category():
    _, report = scrub_text("Call 555-123-4567 or email a@b.co, acct no 1234567890")
    assert report.counts == {"phone": 1, "email": 1, "account": 1}
    assert report.total == 3


def test_report_does_not_count_declined_matches():
    # Both a date and a non-Luhn run are matched by a rule but declined by its
    # guard. A declined match is not a redaction.
    _, report = scrub_text("Period 04-30-2026")
    assert report.counts == {}
    assert report.summary() == "none"


def test_report_summary_is_sorted_and_compact():
    _, report = scrub_text("Call 555-123-4567 and 555-987-6543, ssn 123-45-6789")
    assert report.summary() == "phone=2 ssn=1"


# ── idempotence ─────────────────────────────────────────────────────────────


# ── identifier columns (structural redaction) ───────────────────────────────


# The bank's own export is 10 digits, which the generic 9+ digit rule happens to
# catch. Nothing about that is a design: 7 and 8 digits passed through in full
# before `redact_columns`, and they are the cases that matter here.
@pytest.mark.parametrize(
    "account",
    ["1234", "2122902", "21229022", "212290221", "2122902212", "1234567890123456", "212-2212"],
)
def test_identifier_columns_are_masked_at_every_length(account):
    headers = ["Account Number", "Post Date", "Description", "Amount"]
    rows, report = redact_columns(headers, [[account, "7/30/2026", "PAYROLL", "2541.90"]])

    assert rows[0][0] == f"••{account[-4:].lstrip('-')}"
    assert report.counts["column"] == 1
    # The full value is gone unless it was only ever 4 digits to begin with.
    if len(account.replace("-", "")) > 4:
        assert account not in rows[0][0]


def test_identifier_column_with_too_few_digits_is_fully_masked():
    rows, _ = redact_columns(["Account Number"], [["12"]])
    assert rows[0][0] == "••••"


@pytest.mark.parametrize(
    "header",
    ["Account Number", "account_no", "ACCT#", "Card Number", "Check", "ChkRef", "Routing Number"],
)
def test_sensitive_headers_are_recognized_however_they_are_written(header):
    assert is_sensitive_column(header)
    rows, _ = redact_columns([header], [["2122902212"]])
    assert rows[0][0] == "••2212"


@pytest.mark.parametrize("header", ["Description", "Amount", "Date", "Post Date", "Balance", "Debit"])
def test_transaction_columns_are_left_alone(header):
    assert not is_sensitive_column(header)
    rows, report = redact_columns([header], [["2122902212"]])
    assert rows[0][0] == "2122902212"
    assert report.total == 0


def test_account_column_holding_a_name_is_not_masked():
    # An "Account" column may hold the account's name, which is the signal the
    # orchestrator matches a statement on. Only values with digits are identifiers.
    rows, report = redact_columns(["Account"], [["Bank OZK Checking"]])
    assert rows[0][0] == "Bank OZK Checking"
    assert report.total == 0


@pytest.mark.parametrize(
    "value,masked",
    [
        ("21229022", True),        # bare identifier
        ("2122902212", True),
        ("212-2212", True),
        ("327676", True),
        ("2026-03-01", False),     # a date, which the agent needs to recognize
        ("7/30/2026", False),
        ("54.20", False),          # money keeps its decimal
        ("1200.00", False),
        ("2541", False),           # too short to tell from a whole-dollar amount
        ("SUPERMERCADO", False),
        ("", False),
    ],
)
def test_bare_identifier_masking_for_unrecognized_headers(value, masked):
    # Used only when the header row itself is unknown, so the value's shape is the
    # only signal left. "Numero de Cuenta" is in no alias list.
    rows, _ = redact_columns(["Numero de Cuenta"], [[value]], mask_bare_identifiers=True)
    assert (rows[0][0] != value) is masked


def test_bare_identifier_masking_is_off_by_default():
    rows, _ = redact_columns(["Numero de Cuenta"], [["21229022"]])
    assert rows[0][0] == "21229022"


def test_normalize_header_folds_separators_and_case():
    assert normalize_header("Post Date") == "post date"
    assert normalize_header("post_date") == "post date"
    assert normalize_header("POST-DATE") == "post date"
    assert normalize_header(None) == ""


def test_labelled_id_rule_handles_the_tabular_equals_form():
    # A digest peek renders as "Account Number=21229022". Eight digits is under the
    # generic rule's floor, so the label is the only thing that can catch it.
    assert "[ACCT ••9022]" in scrubbed("Account Number=21229022, Post Date=7/30/2026")
    assert "21229022" not in scrubbed("Account Number=21229022")


# ── peer-to-peer counterparty names ─────────────────────────────────────────


def test_p2p_counterparty_name_is_redacted():
    text = "XX3178 MT DDA DEBIT VENMO  Zach John New York NY CNP TX 327676"
    result = scrub_description(text)
    assert "Zach John" not in result
    assert "[NAME]" in result
    # The rail and the trailing references survive — they are what the classifier
    # reads to recognize this as a peer-to-peer transfer.
    assert "VENMO" in result and "CNP TX" in result


def test_p2p_rule_skips_rail_protocol_words_to_find_the_name():
    assert scrub_description("ZELLE PAYMENT FROM John Smith") == "ZELLE PAYMENT FROM [NAME]"


@pytest.mark.parametrize(
    "text",
    [
        "VENMO CASHOUT 1047963703820",  # CASHOUT is a keyword, and no name follows
        "XX3178 MT DDA DEBIT APPLE CASH SENT 1INFINITELOOP CA VP2P1850 017405",
    ],
)
def test_p2p_rule_does_not_invent_a_name(text):
    assert "[NAME]" not in scrub_description(text)


@pytest.mark.parametrize(
    "text",
    [
        "WAL-MART #5837         ROGERS        AR",
        "CHICK-FIL-A #03901     ROGERS        AR",
        "SQ *WILLIAMS FAMOUS FR Bentonville   AR",
        "CLAUDE.AI SUBSCRIPTION SAN FRANCISCO CA",
    ],
)
def test_merchant_descriptions_are_untouched_by_the_p2p_rule(text):
    # Merchant name and city are the classifier's main signal; only P2P rails,
    # where the "merchant" is a person, lose them.
    assert scrub_description(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "Account Number 1234567890",
        "PAYMENT 4111111111111111",
        "Card ending in 4111 1111 1111 1111",
        "1234 N MAIN ST SPRINGFIELD, IL 62704 Emp #: 123456789",
        "Call 555-123-4567, ssn 123-45-6789, ref 1234567890123456",
        "VENMO  Zach John New York NY CNP TX 327676",
        "Account Number=21229022",
    ],
)
def test_scrubbing_is_idempotent(text):
    once = scrubbed(text)
    assert scrubbed(once) == once


def test_empty_input():
    assert scrub_text("") == ("", scrub_text("")[1])
    assert scrub_text("")[1].total == 0
    assert scrub_description("") == ""
