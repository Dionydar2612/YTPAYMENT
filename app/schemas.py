from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


# ---------- Auth ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class MeResponse(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ---------- Members ----------
class MemberCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    role: str = "member"

    @field_validator("username")
    @classmethod
    def username_len(cls, v):
        if len(v.strip()) < 3:
            raise ValueError("username ต้องมีอย่างน้อย 3 ตัวอักษร")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_len(cls, v):
        if len(v) < 4:
            raise ValueError("password ต้องมีอย่างน้อย 4 ตัวอักษร")
        return v


class MemberUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class MemberOut(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OldBalanceRequest(BaseModel):
    month: str
    amount: Decimal


# ---------- Expenses ----------
class ExpenseCreate(BaseModel):
    month: str
    description: str
    total_amount: Decimal

    @field_validator("month")
    @classmethod
    def month_format(cls, v):
        import re

        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError("month ต้องอยู่ในรูปแบบ YYYY-MM")
        return v

    @field_validator("total_amount")
    @classmethod
    def positive_amount(cls, v):
        if v <= 0:
            raise ValueError("จำนวนเงินต้องมากกว่า 0")
        return v


class ExpenseOut(BaseModel):
    id: str
    month: str
    description: str
    total_amount: Decimal
    participants_count: int
    per_person_amount: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Slips ----------
class SlipCreate(BaseModel):
    month: str
    amount_claimed: Decimal
    transferred_at: Optional[datetime] = None


class SlipOut(BaseModel):
    id: str
    user_id: str
    username: Optional[str] = None
    month: str
    amount_claimed: Decimal
    file_path: str
    transferred_at: Optional[datetime] = None
    status: str
    reject_reason: Optional[str] = None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SlipRejectRequest(BaseModel):
    reason: str


# ---------- Balances / dashboard ----------
class MonthlyBalanceOut(BaseModel):
    month: str
    base_amount: Decimal
    old_balance_carried: Decimal
    credit_used: Decimal
    total_due: Decimal
    total_paid: Decimal
    outstanding: Decimal
    credit_new: Decimal
    status: str

    model_config = ConfigDict(from_attributes=True)


class PaymentOut(BaseModel):
    id: str
    month: str
    amount: Decimal
    note: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ClearOutstandingRequest(BaseModel):
    amount: Optional[Decimal] = None
    note: Optional[str] = None


class CreditTransferRequest(BaseModel):
    from_user_id: str
    source_month: str
    to_user_id: str
    target_month: str
    amount: Decimal
    note: Optional[str] = None
