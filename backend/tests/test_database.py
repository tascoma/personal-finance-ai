from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.databases import Base, init_db
from app.models import (
    Account,
    JournalEntry,
    JournalLine,
    Period,
    StatedBalance,
)

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded_engine():
    """Engine with tables created and CoA seeded via init_db."""
    from app import databases as db_module

    orig_engine = db_module.engine
    orig_session_local = db_module.AsyncSessionLocal

    eng = create_async_engine(TEST_DB_URL, echo=False)
    db_module.engine = eng
    db_module.AsyncSessionLocal = async_sessionmaker(eng, expire_on_commit=False)

    await init_db()

    yield eng

    db_module.engine = orig_engine
    db_module.AsyncSessionLocal = orig_session_local
    await eng.dispose()


@pytest.mark.asyncio
async def test_accounts_seeded(seeded_engine):
    factory = async_sessionmaker(seeded_engine, expire_on_commit=False)
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(Account))
    assert count == 69


@pytest.mark.asyncio
async def test_period_create(session: AsyncSession):
    period = Period(
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        status="open",
    )
    session.add(period)
    await session.commit()
    await session.refresh(period)

    result = await session.get(Period, period.period_id)
    assert result is not None
    assert result.period_start == date(2024, 1, 1)
    assert result.status == "open"


@pytest.mark.asyncio
async def test_journal_entry_balanced(session: AsyncSession):
    # Seed two minimal accounts so FKs resolve
    checking = Account(
        account_code=100101,
        account_name="Checking",
        account_type="Asset",
        sub_category="Cash",
        normal_balance="debit",
    )
    salary = Account(
        account_code=400101,
        account_name="Salary",
        account_type="Income",
        sub_category="Earned Income",
        normal_balance="credit",
    )
    period = Period(
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        status="open",
    )
    session.add_all([checking, salary, period])
    await session.commit()

    entry = JournalEntry(
        period_id=period.period_id,
        entry_date=date(2024, 1, 15),
        description="Payroll",
        source_type="paystub",
        created_by="python",
    )
    session.add(entry)
    await session.flush()

    debit_line = JournalLine(
        entry_id=entry.entry_id,
        account_code=100101,
        debit_amount=Decimal("100.00"),
        credit_amount=Decimal("0.00"),
    )
    credit_line = JournalLine(
        entry_id=entry.entry_id,
        account_code=400101,
        debit_amount=Decimal("0.00"),
        credit_amount=Decimal("100.00"),
    )
    session.add_all([debit_line, credit_line])
    await session.commit()

    lines = (await session.scalars(
        select(JournalLine).where(JournalLine.entry_id == entry.entry_id)
    )).all()
    assert len(lines) == 2
    net = sum(ln.debit_amount - ln.credit_amount for ln in lines)
    assert net == Decimal("0.00")


@pytest.mark.asyncio
async def test_journal_line_check_constraint(session: AsyncSession):
    checking = Account(
        account_code=100101,
        account_name="Checking",
        account_type="Asset",
        sub_category="Cash",
        normal_balance="debit",
    )
    period = Period(
        period_start=date(2024, 2, 1),
        period_end=date(2024, 2, 29),
        status="open",
    )
    session.add_all([checking, period])
    await session.commit()

    entry = JournalEntry(
        period_id=period.period_id,
        entry_date=date(2024, 2, 1),
        description="Bad entry",
        source_type="manual",
        created_by="python",
    )
    session.add(entry)
    await session.flush()

    bad_line = JournalLine(
        entry_id=entry.entry_id,
        account_code=100101,
        debit_amount=Decimal("50.00"),
        credit_amount=Decimal("50.00"),
    )
    session.add(bad_line)
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_stated_balance_unique(session: AsyncSession):
    checking = Account(
        account_code=100101,
        account_name="Checking",
        account_type="Asset",
        sub_category="Cash",
        normal_balance="debit",
    )
    period = Period(
        period_start=date(2024, 3, 1),
        period_end=date(2024, 3, 31),
        status="open",
    )
    session.add_all([checking, period])
    await session.commit()

    b1 = StatedBalance(
        period_id=period.period_id,
        account_code=100101,
        stated_balance=Decimal("1000.00"),
    )
    session.add(b1)
    await session.commit()

    b2 = StatedBalance(
        period_id=period.period_id,
        account_code=100101,
        stated_balance=Decimal("2000.00"),
    )
    session.add(b2)
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_every_model_module_is_exported_from_app_models():
    """Every model class on disk must be re-exported by `app.models`.

    Alembic's autogenerate and `init_db()`'s `create_all` both diff against
    `Base.metadata`, which is populated purely as an import side effect. A model
    that exists on disk but is not imported by `app/models/__init__.py` is
    invisible to both: `create_all` silently skips the table, and the next
    `alembic revision --autogenerate` emits a `drop_table` for it. That is
    exactly what happened to `device_tokens`.

    Note this asserts on the package's *exported attributes*, not on
    `Base.metadata` — importing a module to discover its models would itself
    register them and make the assertion vacuous.
    """
    import importlib
    import pkgutil

    import app.models

    missing: list[str] = []
    for mod in pkgutil.iter_modules(app.models.__path__):
        module = importlib.import_module(f"app.models.{mod.name}")
        for name, obj in vars(module).items():
            if not isinstance(getattr(obj, "__tablename__", None), str):
                continue
            if getattr(obj, "__module__", "") != module.__name__:
                continue  # imported into the module, not defined there
            if getattr(app.models, name, None) is not obj:
                missing.append(f"{mod.name}.{name}")

    assert not missing, (
        f"model(s) not exported from app.models: {sorted(missing)} — add to "
        "app/models/__init__.py so Base.metadata registration is guaranteed"
    )
