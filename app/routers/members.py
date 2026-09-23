from typing import List
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import hash_password, require_admin, get_current_user
from app.database import get_db
from app.models import (
    User,
    UserRole,
    MonthlyBalance,
    Expense,
    ExpenseParticipant,
    Payment,
    PaymentSlip,
)
from app.schemas import MemberCreate, MemberUpdate, MemberOut, OldBalanceRequest
from app.services.calculation import (
    add_old_balance,
    current_month,
    recompute_user_balances,
    _last_known_month,
)

router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("", response_model=List[MemberOut])
def list_members(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.query(User).order_by(User.role.asc(), User.username.asc()).all()


@router.post("", response_model=MemberOut, status_code=201)
def create_member(payload: MemberCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username นี้ถูกใช้แล้ว")
    role = UserRole.admin if payload.role == "admin" else UserRole.member
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: str, payload: MemberUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    user = db.get(User, member_id)
    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบสมาชิก")
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.password:
        user.password_hash = hash_password(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user


def _has_financial_history(db: Session, member_id: str) -> bool:
    """True if the member has ANY record that would be orphaned or lose
    referential integrity if the user row were hard-deleted — i.e. they
    were ever charged for an expense, made a payment, uploaded a slip, or
    created an expense as admin."""
    checks = [
        db.query(ExpenseParticipant.id).filter(ExpenseParticipant.user_id == member_id),
        db.query(Payment.id).filter(Payment.user_id == member_id),
        db.query(PaymentSlip.id).filter(PaymentSlip.user_id == member_id),
        db.query(MonthlyBalance.id).filter(MonthlyBalance.user_id == member_id),
        db.query(Expense.id).filter(Expense.created_by == member_id),
    ]
    return any(db.query(q.exists()).scalar() for q in checks)


@router.delete("/{member_id}")
def delete_member(member_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.get(User, member_id)
    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบสมาชิก")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="ไม่สามารถลบ/ปิดใช้งานบัญชีตนเองได้")

    if _has_financial_history(db, member_id):
        # Deleting would break foreign keys or erase past-month financial
        # records, which the spec explicitly forbids. Fall back to a soft
        # deactivate so history stays intact and viewable in reports.
        user.is_active = False
        db.commit()
        return {
            "ok": True,
            "action": "deactivated",
            "message": "สมาชิกนี้มีประวัติการเงินอยู่แล้ว ระบบจึงปิดใช้งานบัญชีแทนการลบถาวร เพื่อไม่ให้ประวัติค่าใช้จ่าย/การชำระเงินเก่าเสียหาย",
        }

    db.delete(user)
    db.commit()
    return {"ok": True, "action": "deleted", "message": "ลบสมาชิกออกจากระบบแล้ว"}


@router.post("/{member_id}/old-balance")
def set_old_balance(
    member_id: str,
    payload: OldBalanceRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, member_id)
    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบสมาชิก")
    bal = add_old_balance(db, member_id, payload.month, payload.amount)
    return {
        "ok": True,
        "month": bal.month,
        "old_balance_carried": str(bal.old_balance_carried),
        "total_due": str(bal.total_due),
    }


@router.get("/{member_id}/detail")
def member_detail(
    member_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):

    user = db.get(
        User,
        member_id
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="ไม่พบสมาชิก"
        )

    latest_month = _last_known_month(
        db,
        member_id,
        current_month()
    )

    recompute_user_balances(
        db,
        member_id,
        latest_month
    )

    db.commit()

    balances = (
        db.query(MonthlyBalance)
        .filter(
            MonthlyBalance.user_id == member_id
        )
        .order_by(
            MonthlyBalance.month.desc()
        )
        .all()
    )

    total_outstanding = sum(
        (
            Decimal(b.outstanding)
            for b in balances
        ),
        Decimal("0.00")
    )

    total_credit = sum(
        (
            Decimal(b.credit_new)
            for b in balances
        ),
        Decimal("0.00")
    )

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
        },

        "summary": {
            "total_outstanding": str(
                total_outstanding
            ),
            "total_credit": str(
                total_credit
            ),
        },

        "balances": [
            {
                "month": b.month,
                "base_amount": str(
                    b.base_amount
                ),
                "old_balance_carried": str(
                    b.old_balance_carried
                ),
                "credit_used": str(
                    b.credit_used
                ),
                "total_due": str(
                    b.total_due
                ),
                "total_paid": str(
                    b.total_paid
                ),
                "outstanding": str(
                    b.outstanding
                ),
                "credit_new": str(
                    b.credit_new
                ),
                "status": b.status.value,
            }
            for b in balances
        ],
    }
