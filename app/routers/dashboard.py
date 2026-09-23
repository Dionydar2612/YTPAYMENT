from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password
from app.database import get_db
from app.models import (
    User,
    UserRole,
    MonthlyBalance,
    Expense,
    ExpenseParticipant,
    Payment,
    CreditAllocation,
)
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


def month_has_real_data(
    db: Session,
    month: str,
    user_id: str | None = None,
) -> bool:
    """
    ตรวจว่าเดือนนี้มีข้อมูลจริงหรือยัง

    สำคัญ:
    แค่เปิด Dashboard ไม่ถือว่าเป็นข้อมูล
    และไม่ควรสร้าง MonthlyBalance เพียงเพราะเป็นเดือนปัจจุบัน
    """

    # มีค่าใช้จ่ายในเดือนนี้หรือไม่
    expense_query = db.query(Expense.id).filter(
        Expense.month == month
    )

    if user_id:
        expense_query = (
            expense_query
            .join(
                ExpenseParticipant,
                ExpenseParticipant.expense_id == Expense.id,
            )
            .filter(
                ExpenseParticipant.user_id == user_id
            )
        )

    if expense_query.first():
        return True

    # มีการจ่ายเงินในเดือนนี้หรือไม่
    if user_id:
        payment_exists = (
            db.query(Payment.id)
            .filter(
                Payment.user_id == user_id,
                Payment.month == month,
            )
            .first()
        )

        if payment_exists:
            return True

    # มีการโอนเครดิตเข้าเดือนนี้หรือไม่
    if user_id:
        credit_received = (
            db.query(CreditAllocation.id)
            .filter(
                CreditAllocation.target_user_id == user_id,
                CreditAllocation.target_month == month,
            )
            .first()
        )

        if credit_received:
            return True

        # มีการโอนเครดิตออกจากเดือนนี้หรือไม่
        credit_sent = (
            db.query(CreditAllocation.id)
            .filter(
                CreditAllocation.source_user_id == user_id,
                CreditAllocation.source_month == month,
            )
            .first()
        )

        if credit_sent:
            return True

    return False


@router.get("/dashboard")
def dashboard(
    month: str = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    month = month or current_month()

    # ============================================================
    # MEMBER
    # ============================================================

    if user.role == UserRole.member:

        if month_has_real_data(db, month, user.id):
            bal = recompute_user_balances(
                db,
                user.id,
                month,
            )

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

        # ไม่มีข้อมูลจริง → ห้ามสร้าง MonthlyBalance
        return {
            "role": "member",
            "month": month,
            "balance": {
                "base_amount": "0.00",
                "old_balance_carried": "0.00",
                "credit_used": "0.00",
                "credit_source_month": None,
                "total_due": "0.00",
                "total_paid": "0.00",
                "outstanding": "0.00",
                "credit_new": "0.00",
                "status": "paid",
                "total_to_pay_now": "0.00",
            },
        }

    # ============================================================
    # ADMIN
    # ============================================================

    users = (
        db.query(User)
        .order_by(
            User.role.asc(),
            User.username.asc(),
        )
        .all()
    )

    # คำนวณเฉพาะ user ที่เดือนนั้นมีข้อมูลจริง
    for target in users:
        if month_has_real_data(
            db,
            month,
            target.id,
        ):
            recompute_user_balances(
                db,
                target.id,
                month,
            )

    db.commit()

    active_users = [
        u for u in users
        if u.is_active
    ]

    member_count = len(
        [
            u for u in active_users
            if u.role == UserRole.member
        ]
    )

    participants_count = len(active_users)

    expenses_this_month = (
        db.query(Expense)
        .filter(
            Expense.month == month
        )
        .all()
    )

    total_expense = sum(
        (
            e.total_amount
            for e in expenses_this_month
        ),
        start=0,
    )

    balances = (
        db.query(MonthlyBalance)
        .filter(
            MonthlyBalance.month == month
        )
        .all()
    )

    bal_by_user = {
        b.user_id: b
        for b in balances
    }

    collected = sum(
        (
            b.total_paid
            for b in balances
        ),
        start=0,
    )

    outstanding_total = sum(
        (
            b.outstanding
            for b in balances
        ),
        start=0,
    )

    credit_total = sum(
        (
            b.credit_new
            for b in balances
        ),
        start=0,
    )

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

                "base_amount": (
                    str(b.base_amount)
                    if b
                    else "0.00"
                ),

                "old_balance_carried": (
                    str(b.old_balance_carried)
                    if b
                    else "0.00"
                ),

                "credit_used": (
                    str(b.credit_used)
                    if b
                    else "0.00"
                ),

                "total_due": (
                    str(b.total_due)
                    if b
                    else "0.00"
                ),

                "total_paid": (
                    str(b.total_paid)
                    if b
                    else "0.00"
                ),

                "outstanding": (
                    str(b.outstanding)
                    if b
                    else "0.00"
                ),

                "credit_new": (
                    str(b.credit_new)
                    if b
                    else "0.00"
                ),

                "status": (
                    b.status.value
                    if b
                    else "paid"
                ),
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
