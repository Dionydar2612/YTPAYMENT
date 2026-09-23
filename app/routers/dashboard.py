from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password
from app.database import get_db
from app.models import User, UserRole, MonthlyBalance, Expense
from app.schemas import MeResponse
from app.services.calculation import current_month, recompute_user_balances

router = APIRouter(prefix="/api", tags=["dashboard"])


class PasswordChange(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def min_len(cls, v):
        if len(v) < 4:
            raise ValueError("password ต้องมีอย่างน้อย 4 ตัวอักษร")
        return v


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    return user


@router.put("/me/password")
def change_own_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user.password_hash = hash_password(payload.password)
    db.commit()
    return {"ok": True}


@router.get("/dashboard")
def dashboard(
    month: str = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    month = month or current_month()

    if user.role == UserRole.member:
        bal = recompute_user_balances(db, user.id, month)
        db.commit()
        return {
            "role": "member",
            "month": month,
            "balance": {
                "base_amount": str(bal.base_amount),
                "old_balance_carried": str(bal.old_balance_carried),
                "credit_used": str(bal.credit_used),
                "credit_source_month": bal.credit_source_month,
                "total_due": str(bal.total_due),
                "total_paid": str(bal.total_paid),
                "outstanding": str(bal.outstanding),
                "credit_new": str(bal.credit_new),
                "status": bal.status.value,
                "total_to_pay_now": str(bal.outstanding),
            },
        }

    users = db.query(User).order_by(User.role.asc(), User.username.asc()).all()

    # Recalculate every user before showing the admin totals. This prevents
    # stale MonthlyBalance rows from making the multi-user summary incorrect.
    for target in users:
        recompute_user_balances(db, target.id, month)
    db.commit()

    active_users = [u for u in users if u.is_active]
    member_count = len([u for u in active_users if u.role == UserRole.member])
    participants_count = len(active_users)

    expenses_this_month = db.query(Expense).filter(Expense.month == month).all()
    total_expense = sum((e.total_amount for e in expenses_this_month), start=0)

    balances = db.query(MonthlyBalance).filter(MonthlyBalance.month == month).all()
    bal_by_user = {b.user_id: b for b in balances}

    collected = sum((b.total_paid for b in balances), start=0)
    outstanding_total = sum((b.outstanding for b in balances), start=0)
    credit_total = sum((b.credit_new for b in balances), start=0)

    rows = []
    for target in users:
        b = bal_by_user.get(target.id)
        rows.append(
            {
                "user_id": target.id,
                "username": target.username,
                "full_name": target.full_name,
                "role": target.role.value,
                "is_active": target.is_active,
                "base_amount": str(b.base_amount) if b else "0.00",
                "old_balance_carried": str(b.old_balance_carried) if b else "0.00",
                "credit_used": str(b.credit_used) if b else "0.00",
                "total_due": str(b.total_due) if b else "0.00",
                "total_paid": str(b.total_paid) if b else "0.00",
                "outstanding": str(b.outstanding) if b else "0.00",
                "credit_new": str(b.credit_new) if b else "0.00",
                "status": b.status.value if b else "unpaid",
            }
        )

    return {
        "role": "admin",
        "month": month,
        "summary": {
            "member_count": member_count,
            "participants_count": participants_count,
            "total_expense": str(total_expense),
            "collected": str(collected),
            "outstanding_total": str(outstanding_total),
            "credit_total": str(credit_total),
        },
        "rows": rows,
    }
