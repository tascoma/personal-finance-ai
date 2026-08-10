from typing import Literal

from pydantic import BaseModel, Field

AccountType = Literal["Asset", "Liability", "Equity", "Income", "Expense", "Memo Asset*"]
NormalBalance = Literal["debit", "credit"]


class AccountRead(BaseModel):
    account_code: int
    account_name: str
    account_type: str
    sub_category: str
    normal_balance: str
    paystub_mapping: str | None
    is_memo: bool
    is_active: bool

    model_config = {"from_attributes": True}


class AccountCreate(BaseModel):
    account_code: int = Field(gt=0)
    account_name: str = Field(min_length=1)
    account_type: AccountType
    sub_category: str = Field(min_length=1)
    normal_balance: NormalBalance
    paystub_mapping: str | None = None
    is_memo: bool = False


class AccountUpdate(BaseModel):
    """Partial update. Only fields present in the request are applied
    (`is_active=False` archives the account; `True` restores it)."""

    account_name: str | None = Field(default=None, min_length=1)
    account_type: AccountType | None = None
    sub_category: str | None = Field(default=None, min_length=1)
    normal_balance: NormalBalance | None = None
    paystub_mapping: str | None = None
    is_memo: bool | None = None
    is_active: bool | None = None
