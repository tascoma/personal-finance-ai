from typing import Literal, Optional

from pydantic import BaseModel, Field

AccountType = Literal["Asset", "Liability", "Equity", "Income", "Expense", "Memo Asset*"]
NormalBalance = Literal["debit", "credit"]


class AccountRead(BaseModel):
    account_code: int
    account_name: str
    account_type: str
    sub_category: str
    normal_balance: str
    paystub_mapping: Optional[str]
    is_memo: bool
    is_active: bool

    model_config = {"from_attributes": True}


class AccountCreate(BaseModel):
    account_code: int = Field(gt=0)
    account_name: str = Field(min_length=1)
    account_type: AccountType
    sub_category: str = Field(min_length=1)
    normal_balance: NormalBalance
    paystub_mapping: Optional[str] = None
    is_memo: bool = False


class AccountUpdate(BaseModel):
    """Partial update. Only fields present in the request are applied
    (`is_active=False` archives the account; `True` restores it)."""

    account_name: Optional[str] = Field(default=None, min_length=1)
    account_type: Optional[AccountType] = None
    sub_category: Optional[str] = Field(default=None, min_length=1)
    normal_balance: Optional[NormalBalance] = None
    paystub_mapping: Optional[str] = None
    is_memo: Optional[bool] = None
    is_active: Optional[bool] = None
