from datetime import date

from pydantic import BaseModel, Field

from app.agents._base import build_agent, run_agent

SYSTEM_PROMPT = (
    "Extract the most recent mortgage payment that was actually made from a "
    "mortgage statement. The statement reports the payment received during the "
    "period it covers; that is the payment to extract — never the upcoming "
    "payment that has not been paid yet.\n"
    "\n"
    "payment_date: the 'Statement Date' (often near the top of the statement, "
    "next to the account number). Do NOT use 'Next Due Date', 'Payment Due "
    "Date', 'Contractual Due Date', or any field describing a future payment.\n"
    "\n"
    "principal / interest / escrow: take these from the 'Past Payments "
    "Breakdown' (or equivalently labelled 'Paid Last Month' / 'Last Payment "
    "Received') column — these are the amounts that were actually applied. "
    "Do NOT use the 'Explanation of Amount Due' table — that section breaks "
    "down the NEXT (unpaid) payment and will be slightly different.\n"
    "\n"
    "Field meanings:\n"
    "  • principal — the portion applied to reduce the outstanding loan balance\n"
    "  • interest — the borrowing cost charged for the period\n"
    "  • escrow — the total amount deposited into the escrow account this period "
    "(labelled 'escrow', 'escrow payment', or similar; this funds future tax and "
    "insurance bills but is NOT the same as paying them directly)\n"
    "  • property_tax — only when a property tax bill is actually disbursed/paid "
    "from escrow (appears on escrow analysis or disbursement statements, not on "
    "regular monthly payment statements); otherwise 0\n"
    "  • home_insurance — only when a homeowners insurance premium is actually "
    "disbursed/paid from escrow; otherwise 0\n"
    "\n"
    "On a regular monthly payment statement, escrow will be non-zero and "
    "property_tax and home_insurance will typically be 0. "
    "Never infer, compute, or total amounts — only return values explicitly shown."
)


class ExtractedMortgage(BaseModel):
    payment_date: date
    principal: float
    interest: float
    escrow: float = Field(description="The total escrow amount, which may include both property tax and home insurance. ")
    property_tax: float = Field(description="When property tax is payed out of the escrow account")
    home_insurance: float = Field(description="When home insurance is payed out of the escrow account")


agent = build_agent(ExtractedMortgage, SYSTEM_PROMPT)


async def run_mortgage_extractor(text: str) -> ExtractedMortgage:
    return await run_agent(agent, "mortgage extractor", text)
