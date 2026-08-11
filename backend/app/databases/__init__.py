import logging
from collections.abc import AsyncGenerator

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=settings.db_pool_pre_ping,
    connect_args=settings.db_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# fmt: off
# (code, name, type, sub_category, normal_balance, paystub_mapping, is_memo)
_ACCOUNTS_SEED = [
    (100101, "Checking – Bank OZK",               "Asset",       "Cash & Cash Equivalents",              "debit",  None,                      False),
    (100102, "Cash on Hand",                       "Asset",       "Cash & Cash Equivalents",              "debit",  None,                      False),
    (100103, "Venmo Balance",                      "Asset",       "Cash & Cash Equivalents",              "debit",  None,                      False),
    (100201, "HSA – Cash",                         "Asset",       "Restricted Cash",                      "debit",  "HSA CONTR *",             False),
    (100202, "Escrow Account",                     "Asset",       "Restricted Cash",                      "debit",  None,                      False),
    (110101, "EJ – Brokerage (Single Account)",    "Asset",       "Investments",                          "debit",  None,                      False),
    (110102, "Computer Share – ASPP",              "Asset",       "Investments",                          "debit",  "CO STK CONT|STOCK PURCH", False),
    (110103, "Coinbase – Crypto",                  "Asset",       "Investments",                          "debit",  None,                      False),
    (111101, "EJ – Roth IRA",                      "Asset",       "Retirement & Tax-Advantaged Accounts", "debit",  None,                      False),
    (111102, "Merrill – Roth 401(k)",              "Asset",       "Retirement & Tax-Advantaged Accounts", "debit",  "ROTH 401K",               False),
    (111103, "HSA – Investments",                  "Asset",       "Retirement & Tax-Advantaged Accounts", "debit",  None,                      False),
    (112101, "Fidelity – RSUs (Vested)",           "Asset",       "Investments",                          "debit",  None,                      False),
    (112102, "Fidelity – RSUs (Unvested)",         "Memo Asset*", "Equity Compensation (Off-BS)",         "debit",  None,                      True),
    (120101, "Primary Residence",                  "Asset",       "Real Estate",                          "debit",  None,                      False),
    (200101, "EJ Mastercard",                      "Liability",   "Credit Cards",                         "credit", None,                      False),
    (210101, "Loan Payable – Parents",             "Liability",   "Long-Term Debt",                       "credit", None,                      False),
    (210102, "Mortgage Payable",                   "Liability",   "Long-Term Debt",                       "credit", None,                      False),
    (300101, "Owner's Equity",                     "Equity",      "Contributed Capital",                  "credit", None,                      False),
    (300102, "Prior Period Net Worth",             "Equity",      "Retained Equity",                      "credit", None,                      False),
    (300103, "Current Period Net Income",          "Equity",      "Earnings",                             "credit", None,                      False),
    (400101, "Salary – Regular Earnings",          "Income",      "Earned Income",                        "credit", "REGULAR EARNING",         False),
    (400102, "Management Incentive / Bonus",       "Income",      "Variable Compensation",                "credit", "MGMT INCENTIVE",          False),
    (400103, "Equity Compensation – RSUs",         "Income",      "Equity Compensation",                  "credit", "RS/RSU GROSS",            False),
    (400104, "Employer Stock Contribution",        "Income",      "Equity Compensation",                  "credit", "CO STK CONT",             False),
    (400106, "Employer 401(k) Match",             "Income",      "Employer Benefits",                    "credit", None,                      False),
    (410101, "Capital Gains – Realized",           "Income",      "Investment Income",                    "credit", None,                      False),
    (410102, "Capital Losses – Realized",          "Income",      "Investment Income",                    "debit",  None,                      False),
    (410103, "Unrealized Market Gain/Loss",         "Income",      "Investment Income",                    "credit", None,                      False),
    (510101, "Mortgage Interest",                  "Expense",     "Housing",                              "debit",  None,                      False),
    (510102, "Property Taxes",                     "Expense",     "Housing",                              "debit",  None,                      False),
    (510103, "Home Insurance",                     "Expense",     "Housing",                              "debit",  None,                      False),
    (510104, "Electricity",                        "Expense",     "Utilities",                            "debit",  None,                      False),
    (510105, "Natural Gas",                        "Expense",     "Utilities",                            "debit",  None,                      False),
    (510106, "Water, Sewer & Trash",               "Expense",     "Utilities",                            "debit",  None,                      False),
    (510109, "Home Repairs & Maintenance",         "Expense",     "Housing",                              "debit",  None,                      False),
    (510110, "Yard & Lawn Maintenance",            "Expense",     "Housing",                              "debit",  None,                      False),
    (520101, "Groceries",                          "Expense",     "Food",                                 "debit",  None,                      False),
    (520102, "Dining Out",                         "Expense",     "Food",                                 "debit",  None,                      False),
    (520103, "Alcohol",                            "Expense",     "Food",                                 "debit",  None,                      False),
    (520104, "Household Supplies",                 "Expense",     "Housing",                              "debit",  None,                      False),
    (530201, "Fuel",                               "Expense",     "Transportation",                       "debit",  None,                      False),
    (530202, "Auto Insurance",                     "Expense",     "Transportation",                       "debit",  None,                      False),
    (530203, "Vehicle Maintenance & Repairs",      "Expense",     "Transportation",                       "debit",  None,                      False),
    (530204, "Registration & Taxes",               "Expense",     "Transportation",                       "debit",  None,                      False),
    (530205, "Parking & Tolls",                    "Expense",     "Transportation",                       "debit",  None,                      False),
    (530206, "Car Wash",                           "Expense",     "Transportation",                       "debit",  None,                      False),
    (530207, "Ride Services (Uber, Lyft)",         "Expense",     "Transportation",                       "debit",  None,                      False),
    (540101, "Mobile Phone",                       "Expense",     "Communications",                       "debit",  None,                      False),
    (540102, "Internet",                           "Expense",     "Communications",                       "debit",  None,                      False),
    (540103, "Streaming Services",                 "Expense",     "Subscriptions",                        "debit",  None,                      False),
    (540104, "Software Subscriptions",             "Expense",     "Subscriptions",                        "debit",  None,                      False),
    (540105, "Cloud Storage",                      "Expense",     "Subscriptions",                        "debit",  None,                      False),
    (550101, "Travel",                             "Expense",     "Lifestyle",                            "debit",  None,                      False),
    (550102, "Entertainment",                      "Expense",     "Lifestyle",                            "debit",  None,                      False),
    (550103, "Hobbies & Recreation",               "Expense",     "Lifestyle",                            "debit",  None,                      False),
    (550104, "Clothing",                           "Expense",     "Personal",                             "debit",  None,                      False),
    (550105, "Grooming & Haircuts",                "Expense",     "Personal",                             "debit",  None,                      False),
    (550106, "Personal Care",                      "Expense",     "Personal",                             "debit",  None,                      False),
    (550107, "Electronics & Technology",           "Expense",     "Lifestyle",                            "debit",  None,                      False),
    (560102, "Charitable Contributions – Payroll", "Expense",     "Giving",                               "debit",  "ACNT",                    False),
    (570101, "Federal Income Tax",                 "Expense",     "Payroll Taxes",                        "debit",  "FEDERAL TAX",             False),
    (570102, "State Income Tax – Arkansas",        "Expense",     "Payroll Taxes",                        "debit",  "ARKANSAS",                False),
    (570103, "FICA – Social Security",             "Expense",     "Payroll Taxes",                        "debit",  "SOCIAL SECURITY",         False),
    (570104, "FICA – Medicare",                    "Expense",     "Payroll Taxes",                        "debit",  "MEDICARE",                False),
    (580101, "Health Insurance – Medical",         "Expense",     "Employee Benefits",                    "debit",  "INS MED U *",             False),
    (580102, "Health Insurance – Dental",          "Expense",     "Employee Benefits",                    "debit",  "INS DEN U *",             False),
    (580103, "Health Insurance – Vision",          "Expense",     "Employee Benefits",                    "debit",  "INS VIS *",               False),
    (580104, "Health Club / Wellness",             "Expense",     "Employee Benefits",                    "debit",  "HEALTH CLUB",             False),
    (999999, "Suspense",                           "Expense",     "Suspense",                             "debit",  None,                      False),
]
# fmt: on


async def _seed_accounts_if_empty() -> None:
    from app.models.account import Account

    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(Account))
        if count and count > 0:
            return
        rows = [
            Account(
                account_code=code,
                account_name=name,
                account_type=acct_type,
                sub_category=sub_cat,
                normal_balance=normal_bal,
                paystub_mapping=paystub,
                is_memo=is_memo,
            )
            for code, name, acct_type, sub_cat, normal_bal, paystub, is_memo in _ACCOUNTS_SEED
        ]
        session.add_all(rows)
        await session.commit()
        logger.info("Seeded %d accounts into Chart of Accounts", len(rows))


async def init_db() -> None:
    # Importing the package registers every model on Base.metadata via
    # app/models/__init__.py. Import the package rather than re-listing each
    # model here: a per-model list has to be kept in sync with alembic/env.py
    # and app/models/__init__.py, and drifting out of sync is what previously
    # left `device_tokens` out of create_all entirely.
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_accounts_if_empty()
