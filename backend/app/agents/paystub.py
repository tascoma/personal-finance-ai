from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.agents._base import build_agent, run_agent

SYSTEM_PROMPT = (
    "Extract ALL pay periods found in the document — some paystubs include "
    "more than one period (e.g. current period on page 1, prior period on page 2). "
    "For each period, preserve the exact payroll labels "
    "(e.g. 'REGULAR EARNING', 'ROTH 401K', 'INS MED U PT', 'FEDERAL TAX'). "
    "Classify each line as earning, deduction, tax, or net_pay. Do not sum "
    "or transform amounts. Omit any line item whose amount is zero."
)


class PaystubLine(BaseModel):
    label: str
    amount: Decimal
    kind: Literal["earning", "deduction", "tax", "net_pay"]


class ExtractedPaystub(BaseModel):
    pay_date: date
    lines: list[PaystubLine]
    gross_pay: Decimal
    net_pay: Decimal


class ExtractedPaystubs(BaseModel):
    paystubs: list[ExtractedPaystub]


agent = build_agent(ExtractedPaystubs, SYSTEM_PROMPT)


async def run_paystub_extractor(text: str) -> ExtractedPaystubs:
    output = await run_agent(agent, "paystub extractor", text)
    for paystub in output.paystubs:
        paystub.lines = [line for line in paystub.lines if line.amount != 0]
    return output
