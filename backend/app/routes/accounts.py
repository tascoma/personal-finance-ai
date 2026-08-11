import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db_session
from app.models.account import Account
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["accounts"], dependencies=[Depends(get_current_user)])


@router.get("/accounts", response_model=list[AccountRead])
async def list_accounts(
    db: AsyncSession = Depends(get_db_session),
    include_inactive: bool = Query(
        default=False, description="Include archived (is_active=False) accounts."
    ),
) -> list[AccountRead]:
    stmt = select(Account).order_by(Account.account_code)
    if not include_inactive:
        stmt = stmt.where(Account.is_active.is_(True))
    result = await db.scalars(stmt)
    return [AccountRead.model_validate(a) for a in result.all()]


@router.post("/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreate,
    db: AsyncSession = Depends(get_db_session),
) -> AccountRead:
    if await db.get(Account, body.account_code) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Account code {body.account_code} already exists",
        )
    account = Account(**body.model_dump())
    db.add(account)
    await db.commit()
    await db.refresh(account)
    logger.info("Created account %d (%s)", account.account_code, account.account_name)
    return AccountRead.model_validate(account)


@router.patch("/accounts/{account_code}", response_model=AccountRead)
async def update_account(
    account_code: int,
    body: AccountUpdate,
    db: AsyncSession = Depends(get_db_session),
) -> AccountRead:
    account = await db.get(Account, account_code)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    updates = body.model_dump(exclude_unset=True)

    # Archiving an account that still has activity in a non-closed period would
    # leave that balance out of the period close (the close sweep filters on
    # is_active). Block it until the period is closed.
    if updates.get("is_active") is False:
        open_activity = await db.scalar(
            select(JournalLine.account_code)
            .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
            .join(Period, JournalEntry.period_id == Period.period_id)
            .where(JournalLine.account_code == account_code, Period.status != "closed")
            .limit(1)
        )
        if open_activity is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot archive an account with activity in an open period; close the period first.",
            )

    for field, value in updates.items():
        setattr(account, field, value)
    await db.commit()
    await db.refresh(account)
    logger.info("Updated account %d: %s", account_code, ", ".join(updates) or "(no changes)")
    return AccountRead.model_validate(account)
