"""Deterministic PII/PCI redaction applied at the LLM boundary.

Statement text is scrubbed on its way out to Anthropic, not on its way into the
database: `raw_transactions.description` and the journal stay verbatim so the
dedup hash in `app.services.parse` and the audit trail still match the source
document. Nothing here is probabilistic — no NER, no model, no confidence
scores. Same input, same output, every time.

No DB, no network, no LLM. Callers pass `keep_terms` (the user's
chart-of-accounts names) because two signals have to survive the scrub or the
pipeline breaks:

  - The institution / product name. `app.agents.orchestrator` matches a
    statement to its source account on that name.
  - The last 4 digits of an account number, which the same prompt uses as its
    fallback match. Every replacement below therefore keeps the last 4 digits.

Amounts, dates, and payroll labels are never touched: the paystub extractor
matches labels against `Account.paystub_mapping`, and the amounts are the whole
point of the extraction.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger(__name__)

MASK = "••"  # "••" — precedes a preserved last-4

# Sentinel used to park `keep_terms` while the rules run. NUL cannot appear in
# pdfplumber output or a CSV cell, so it can never collide with real content.
_SENTINEL = "\x00K{}\x00"
_SENTINEL_RE = re.compile(r"\x00K(\d+)\x00")

US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO"
    "|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)

STREET_SUFFIXES = (
    "ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|BOULEVARD|DR|DRIVE|LN|LANE|CT|COURT|WAY"
    "|PL|PLACE|TER|TERRACE|CIR|CIRCLE|HWY|HIGHWAY|PKWY|PARKWAY|TRL|TRAIL|SQ|SQUARE"
)

# Labels that introduce an identifier. `emp`/`employee` catches the 9-digit
# employee number printed beside the mailing address on every paystub.
ID_LABELS = "account|acct|card|member|loan|policy|routing|emp|employee"

# Columns whose values are identifiers, matched by header name. In a spreadsheet the
# header already says what the column is, so `redact_columns` masks it structurally
# rather than hoping a digit-run rule catches it: the generic rule needs 9+ digits,
# so a 7- or 8-digit account number would otherwise pass through in full.
SENSITIVE_COLUMN_ALIASES = (
    "account number", "account no", "account num", "account", "acct", "acct no",
    "card number", "card no", "card", "member number", "member id", "member no",
    "routing", "routing number", "aba",
    "check", "check number", "check no", "chkref", "chk ref", "ref", "reference",
    "ssn", "tax id", "tin", "customer id", "customer number",
)


# ── patterns ────────────────────────────────────────────────────────────────


_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# 13-19 digits, or four groups of 4 separated consistently by a space or a dash.
# Each alternative is greedy from the leftmost position, so a dashed PAN is always
# consumed whole and a leading dash ("Card No-4111...") can't hide one.
_PAN_RE = re.compile(
    r"(?<![\d.,])(?:\d{13,19}|\d{4}(?:-\d{4}){3}|\d{4}(?: \d{4}){3})(?![\d.,])"
)

# No trailing \b on the label: pdfplumber collapses "Account Number" into the
# single token "AccountNumber" on real statements, and the qualifier group has to
# be free to pick up the glued-on "Number".
_LABELLED_ID_RE = re.compile(
    rf"\b({ID_LABELS})"                                      # 1: the label
    r"(\s*(?:nos?\.?|numbers?|#|ids?|ending(?:\s+in)?))?"     # 2: optional qualifier
    # `=` is in the class because tabular peeks render as "Account Number=2122902212";
    # without it the label sits right beside the value and buys nothing.
    r"(\s*[:#=-]?\s*)"                                       # 3: separator
    r"([Xx*•\d](?:[Xx*•\d-]|\ (?=[Xx*•\d])){3,})"   # 4: the value
    # A letter straight after the digits means this is not an identifier: in a
    # space-collapsed PDF, "LoanNumber:6203S37THST" is the property address, and
    # masking "6203" would mangle it into "[ACCT ••6203]S37THST". Trailing digits
    # are rejected too — otherwise the value group just backtracks off its last
    # digit to satisfy the guard, which both matches anyway and reports a last-4
    # that is shifted by one.
    r"(?![\dA-Za-z])",
    re.IGNORECASE,
)

# Bare digit runs of 9+, dashes allowed — mail-routing barcodes, ACH trace refs,
# ZIP+4. The lookarounds keep it off money: a run may not start after `$`, a
# digit, or a digit-then-separator, and may not be followed by a digit or by a
# separator-then-digit. A plain trailing comma is fine — the digest peek renders
# as "Description=REF 8829384719283, ChkRef=".
_LONG_NUMBER_RE = re.compile(r"(?<![\d$])(?<![\d][.,])\d[\d-]{7,}\d(?![\d])(?![.,]\d)")

# Dates _LONG_NUMBER_RE would otherwise swallow, e.g. 04-30-2026.
_DATE_LIKE_RE = re.compile(r"^(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}-\d{2,4})$")

# Peer-to-peer rails put a counterparty's real name in the memo — "VENMO Zach John
# New York NY CNP TX 327676". No pattern rule finds a bare name, but the rail token
# in front of it is a reliable anchor, so the name is redacted by position instead.
P2P_RAILS = (
    "WESTERN UNION|SQUARE CASH|APPLE CASH|CASH ?APP|MONEYGRAM|POPMONEY"
    "|VENMO|ZELLE|PAYPAL"
)

# Rail protocol words that sit between the rail and the name. Skipped rather than
# treated as the name, so "ZELLE PAYMENT FROM John Smith" still redacts the person.
_P2P_SKIP = (
    "PAYMENTS?|TRANSFERS?|FROM|TO|SENT|RECEIVED|CASH ?OUT|CASHOUT"
    "|XFER|DEBIT|CREDIT|INST|PMT|DES|ID|REF"
)

# A name-shaped word needs a lowercase letter straight after the capital, which is
# what separates "Zach"/"John" from the all-caps trailing refs ("NY", "CNP", "TX")
# and from tokens that open with a digit ("1INFINITELOOP"). That guard is also what
# terminates the run — matching stops at the first token that isn't name-shaped.
_NAME_WORD = r"[A-Z][a-z][A-Za-z'\-]*"

# The rail and the skip words are case-insensitive; the name group must NOT be, or
# the lowercase-letter guard stops discriminating. Hence the scoped `(?i:...)`
# groups rather than a flag on the whole pattern.
_P2P_COUNTERPARTY_RE = re.compile(
    rf"\b(?i:{P2P_RAILS})\b"
    rf"(?:[ \t]+(?i:{_P2P_SKIP})\b)*"
    rf"(?P<name>(?:[ \t]+{_NAME_WORD}){{1,4}})"
)

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")

# A real separator is required between all three groups, so this can't eat a
# bare 10-digit run (that is _LONG_NUMBER_RE's job) or a dollar amount.
# Separators are intra-line only: `\s` would let a match span a line break and
# silently weld two unrelated lines together.
_PHONE_RE = re.compile(
    r"(?<![\d-])(?:\+?1[-.  \t])?(?:\(\d{3}\)[ \t]?|\d{3}[-.  \t])\d{3}[-.  \t]\d{4}(?![\d-])"
)

# Every separator is optional. Some servicers' PDFs extract with no spaces at
# all — "ROGERSAR72758", "Dallas,TX75379-9063" — and a mandatory space between
# the state and the ZIP made this rule miss the address entirely.
_CITY_STATE_ZIP_RE = re.compile(
    rf"\b[A-Z][A-Za-z.\-']*(?:[ ][A-Z][A-Za-z.\-']*){{0,3}}[ \t]*,?[ \t]*"
    rf"(?:{US_STATES})[ \t]*\d{{5}}(?:-\d{{4}})?\b"
)

# The leading lookbehind stops the house number being read out of a date: on a
# real paystub the mailing address follows the deposit date on the same line, so
# "Deposit Date: 05/21/2026 123 MAIN ST" would otherwise match from "2026" and
# take the year with it.
# The unit designator, shared by both street patterns. The second alternative
# covers the bare "<letters>#<digits>" form real statements use — "C#211" — which
# carries no APT/STE keyword to key off.
_UNIT = (
    r"(?:[ \t]*(?:(?:APT|APARTMENT|STE|SUITE|UNIT|RM|ROOM|BLDG|LOT)\.?[ \t]*#?[ \t]*[\w-]+"
    r"|[A-Z]{0,3}#[ \t]*\d+[A-Z]?))?"
)

# Two street patterns rather than one with optional separators. A single pattern
# that allows zero-width separators lets the suffix attach to the tail of an
# ordinary word — "Total 100 Interest" matches as <100> <Intere> <st> — which
# would redact financial text. So: spaced addresses require whole-token
# separators and a whole-token suffix, and glued addresses (some servicers'
# PDFs extract with no spaces at all: "6203S37THST") are matched separately and
# case-sensitively, where an uppercase run before the suffix is the signal.
_STREET_SPACED_RE = re.compile(
    rf"(?<![/.\-])\b\d{{1,6}}[ \t]+(?:[A-Za-z0-9][\w.\-']*[ \t]+){{0,4}}"
    rf"\b(?:{STREET_SUFFIXES})\b\.?{_UNIT}",
    re.IGNORECASE,
)

_STREET_GLUED_RE = re.compile(
    rf"(?<![/.\-])\b\d{{1,6}}[A-Z][A-Z0-9.\-']*(?:{STREET_SUFFIXES})\b{_UNIT}"
)

# A mailing address can survive as fragments around a leftover unit number —
# "[ADDRESS] C#211 [CITY, ST ZIP]" still leaks it. Whatever short thing sits
# between a street match and a city/state/ZIP match belongs to that address, in
# whatever form ("C#211", "Apt 4B", "Bldg 2", "Fl 3"), so collapse the gap. Bound
# it by length and reject `$` so a stray money column can never be swallowed.
_ADDRESS_GAP_RE = re.compile(r"\[ADDRESS\][ \t]*[^\n$]{1,20}?[ \t]*\[CITY, ST ZIP\]")

_PO_BOX_RE = re.compile(r"\bP\.?[ \t]?O\.?[ \t]?BOX[ \t]*#?[ \t]*\d+", re.IGNORECASE)

_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)


@dataclass(slots=True)
class ScrubReport:
    """How many redactions fired, by category. Safe to log — counts only."""

    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def summary(self) -> str:
        """Compact ``account=3 phone=2`` rendering for log lines."""
        if not self.counts:
            return "none"
        return " ".join(f"{k}={v}" for k, v in sorted(self.counts.items()))


# ── public API ──────────────────────────────────────────────────────────────


def scrub_text(text: str, *, keep_terms: Sequence[str] = ()) -> tuple[str, ScrubReport]:
    """Redact a whole document's text before it becomes an LLM prompt.

    Applies the identifier rules plus the address rules. Returns the scrubbed
    text and a count-only report.
    """
    return _scrub(text, keep_terms=keep_terms, addresses=True)


def scrub_description(text: str, *, keep_terms: Sequence[str] = ()) -> str:
    """Redact a single transaction memo, JE description, or filename.

    Identifier rules only. The address rules are skipped because merchant
    strings legitimately look like addresses — "1200 BROADWAY MARKET" is a store
    name, not a mailing address — and over-redacting them costs the classifier
    the signal it needs.
    """
    scrubbed, _ = _scrub(text, keep_terms=keep_terms, addresses=False)
    return scrubbed


def scrub_descriptions_for_prompt(
    texts: Sequence[str], *, keep_terms: Sequence[str] = (), context: str = "prompt"
) -> list[str]:
    """Scrub a batch of descriptions, honoring the `scrub_before_llm` setting.

    The settings gate was re-implemented at five call sites with three different
    behaviors when disabled: two logged a warning, two logged nothing, and one
    silently passed the text through. Route the gate through here so turning the
    escape hatch off is always visible in the logs.
    """
    if not settings.scrub_before_llm:
        logger.warning(
            "PII scrubbing disabled (SCRUB_BEFORE_LLM=false); sending raw text to the LLM for %s",
            context,
        )
        return list(texts)
    return [scrub_description(t, keep_terms=keep_terms) for t in texts]


def last4(value: str) -> str:
    """Return a ``••1234`` mask, or ``••••`` when fewer than 4 digits are present."""
    digits = re.sub(r"\D", "", value)
    return f"{MASK}{digits[-4:]}" if len(digits) >= 4 else f"{MASK}{MASK}"


def normalize_header(value: object) -> str:
    """Fold a spreadsheet header to its comparable form.

    ``Post Date``, ``post_date``, ``POST-DATE`` and ``Post.Date`` are the same
    column wearing four hats. `app.services.statement_mapper` matches its column
    aliases through this too, so both modules agree on what a header "is".
    """
    text = "" if value is None else str(value)
    return re.sub(r"[\s_\-./#]+", " ", text).strip().lower()


_SENSITIVE_HEADERS = frozenset(normalize_header(a) for a in SENSITIVE_COLUMN_ALIASES)


def is_sensitive_column(header: object) -> bool:
    """True when a column's header names it an identifier column."""
    return normalize_header(header) in _SENSITIVE_HEADERS


def looks_like_bare_identifier(text: str) -> bool:
    """True for a value that is only a long run of digits — an ID, not a number.

    Money carries a decimal ("54.20") and dates carry separators in date positions,
    so both are left readable. Six digits is the floor: shorter runs are as likely
    to be a whole-dollar amount as a reference.
    """
    stripped = text.strip()
    if not stripped or _DATE_LIKE_RE.match(stripped) or "/" in stripped:
        return False
    if not re.fullmatch(r"[\d-]+", stripped):
        return False
    return len(re.sub(r"\D", "", stripped)) >= 6


def redact_columns(
    headers: Sequence[object],
    rows: Sequence[Sequence[object]],
    *,
    mask_bare_identifiers: bool = False,
) -> tuple[list[list[str]], ScrubReport]:
    """Mask identifier columns by header name, before any pattern rule runs.

    Structural redaction, not pattern matching: the header names the column, so
    masking does not depend on the value's length or punctuation. A 7-digit
    account number and a 16-digit one are both reduced to their last 4 — which
    `app.agents.orchestrator` still needs to match a statement to its account.

    Only cells containing a digit are masked. A column headed ``Account`` may
    hold the account's *name* ("Bank OZK Checking"), and that is a routing signal
    the orchestrator depends on, not an identifier.

    `mask_bare_identifiers` adds a value-shape rule on top, for callers handling a
    file whose headers are not recognized at all — "Numero de Cuenta" is an account
    column that no alias list knows, and its digits may be too few for the generic
    rule to catch. Off by default: on a known layout the header is the better
    signal, and this would also mask a whole-dollar amount.
    """
    report = ScrubReport()
    sensitive = {i for i, h in enumerate(headers) if is_sensitive_column(h)}

    out: list[list[str]] = []
    for row in rows:
        redacted: list[str] = []
        for i, cell in enumerate(row):
            text = "" if cell is None else str(cell)
            by_header = i in sensitive and any(c.isdigit() for c in text)
            by_shape = mask_bare_identifiers and looks_like_bare_identifier(text)
            if by_header or by_shape:
                redacted.append(last4(text))
                report.counts["column"] = report.counts.get("column", 0) + 1
            else:
                redacted.append(text)
        out.append(redacted)
    return out, report


# ── rule engine ─────────────────────────────────────────────────────────────


def _scrub(text: str, *, keep_terms: Sequence[str], addresses: bool) -> tuple[str, ScrubReport]:
    report = ScrubReport()
    if not text:
        return text, report

    # Identity terms run before keep_terms are parked, so a configured name wins
    # over an account name that happens to contain it ("Scoma Family Checking").
    # Privacy beats source-account matching; the account can be renamed.
    working = _apply_identity_terms(text, settings.pii_identity_term_list, report)

    working, parked = _park_keep_terms(working, keep_terms)

    # Order matters: every specific rule runs before the generic long-number
    # catch-all, or that rule eats the digits the specific ones key off. A phone
    # number and a ZIP+4 are both just long digit runs until proven otherwise.
    working = _sub_literal(_SSN_RE, "[SSN]", working, report, "ssn")
    working = _sub_callback(_PAN_RE, _replace_pan, working, report, "card")
    working = _sub_callback(_LABELLED_ID_RE, _replace_labelled_id, working, report, "account")
    working = _sub_callback(
        _P2P_COUNTERPARTY_RE, _replace_p2p_counterparty, working, report, "counterparty"
    )
    working = _sub_literal(_EMAIL_RE, "[EMAIL]", working, report, "email")
    working = _sub_literal(_PHONE_RE, "[PHONE]", working, report, "phone")

    if addresses:
        working = _sub_literal(_PO_BOX_RE, "[ADDRESS]", working, report, "address")
        working = _sub_literal(_STREET_SPACED_RE, "[ADDRESS]", working, report, "address")
        working = _sub_literal(_STREET_GLUED_RE, "[ADDRESS]", working, report, "address")
        working = _sub_literal(_CITY_STATE_ZIP_RE, "[CITY, ST ZIP]", working, report, "address")
        working = _sub_literal(
            _ADDRESS_GAP_RE, "[ADDRESS] [CITY, ST ZIP]", working, report, "address"
        )

    working = _sub_literal(_URL_RE, "[URL]", working, report, "url")
    working = _sub_callback(_LONG_NUMBER_RE, _replace_long_number, working, report, "number")

    return _restore_keep_terms(working, parked), report


def _apply_identity_terms(text: str, terms: Sequence[str], report: ScrubReport) -> str:
    """Redact configured identity strings — names and street addresses.

    Regexes can find structured identifiers; a person's name has no structure,
    so it is matched literally from settings. Longest first, so "Anthony Scoma"
    is replaced as one unit instead of leaving "Anthony " beside a "[NAME]".

    Whitespace inside a term is treated as optional, because some PDFs extract
    with the spaces stripped — a configured "Michael Anthony" has to match
    "MICHAELANTHONY" too.
    """
    for term in sorted({t for t in terms if t}, key=len, reverse=True):
        pattern = r"\s*".join(re.escape(token) for token in term.split())
        text, hits = re.subn(pattern, "[NAME]", text, flags=re.IGNORECASE)
        if hits:
            report.counts["identity"] = report.counts.get("identity", 0) + hits
    # Adjacent terms ("Michael Anthony" then "Scoma") leave "[NAME][NAME]".
    return re.sub(r"\[NAME\](?:[ \t]*\[NAME\])+", "[NAME]", text)


def _park_keep_terms(text: str, keep_terms: Sequence[str]) -> tuple[str, list[str]]:
    """Swap each keep_term occurrence for a sentinel so no rule can chew on it.

    Longest first, so "Bank OZK Checking" is parked whole rather than leaving a
    " Checking" fragment behind for a later rule to mangle.
    """
    parked: list[str] = []

    def park(match: re.Match[str]) -> str:
        parked.append(match.group(0))
        return _SENTINEL.format(len(parked) - 1)

    for term in sorted({t.strip() for t in keep_terms if t and t.strip()}, key=len, reverse=True):
        text = re.sub(re.escape(term), park, text, flags=re.IGNORECASE)
    return text, parked


def _restore_keep_terms(text: str, parked: list[str]) -> str:
    return _SENTINEL_RE.sub(lambda m: parked[int(m.group(1))], text)


def _sub_literal(
    pattern: re.Pattern[str], replacement: str, text: str, report: ScrubReport, category: str
) -> str:
    new_text, hits = pattern.subn(replacement, text)
    if hits:
        report.counts[category] = report.counts.get(category, 0) + hits
    return new_text


def _sub_callback(
    pattern: re.Pattern[str], replacer, text: str, report: ScrubReport, category: str
) -> str:
    """Like `_sub_literal`, but only counts matches the replacer actually changed.

    The Luhn, already-masked, and date guards all decline a match by returning it
    untouched, and a declined match is not a redaction.
    """

    def counted(match: re.Match[str]) -> str:
        result = replacer(match)
        if result != match.group(0):
            report.counts[category] = report.counts.get(category, 0) + 1
        return result

    return pattern.sub(counted, text)


def _replace_pan(match: re.Match[str]) -> str:
    """Mask a card number only when it passes Luhn.

    Luhn is what makes this rule deterministic and safe: a 16-digit ACH trace
    number or a mail-routing barcode fails the check and falls through to the
    generic long-number rule, while a real PAN is always caught. Length alone
    would only guess.
    """
    raw = match.group(0)
    return f"[CARD {last4(raw)}]" if _luhn_ok(raw) else raw


def _replace_labelled_id(match: re.Match[str]) -> str:
    """Keep the label and qualifier, mask the value.

    The label matters — the orchestrator reads "Account Number ••7890" as an
    account reference and can still match on the last 4.
    """
    label, qualifier, separator, value = match.groups()
    # Already masked by an earlier rule (or by a previous scrub of the same
    # text): leave it alone so scrubbing stays idempotent.
    if MASK in value or len(re.sub(r"\D", "", value)) < 4:
        return match.group(0)
    return f"{label}{qualifier or ''}{separator or ' '}[ACCT {last4(value)}]"


def _replace_p2p_counterparty(match: re.Match[str]) -> str:
    """Mask the name run after a P2P rail, keeping the rail and everything after it.

    The counterparty's city is swallowed along with the name — "Zach John New York"
    all becomes ``[NAME]`` — which is the right call: on a person-to-person transfer
    the city identifies the person, not a merchant location worth classifying on.
    """
    name = match.group("name")
    if MASK in name or "[NAME]" in name:
        return match.group(0)
    prefix = match.group(0)[: match.start("name") - match.start(0)]
    return f"{prefix} [NAME]"


def _replace_long_number(match: re.Match[str]) -> str:
    raw = match.group(0)
    return raw if _DATE_LIKE_RE.match(raw) else f"[NUM {last4(raw)}]"


def _luhn_ok(value: str) -> bool:
    digits = [int(c) for c in value if c.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0
