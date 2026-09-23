from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import MonthlyBalance, Payment, PaymentSlip, User, UserRole
from app.services.calculation import recompute_user_balances, _last_known_month

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def get_history(user_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target_id = user.id
    if user_id and user.role == UserRole.admin:
        target_id = user_id
    elif user_id and user_id != user.id:
        raise HTTPException(status_code=403, detail="ไม่สามารถดูประวัติของสมาชิกคนอื่นได้")

    latest_month = _last_known_month(db, target_id, "1900-01")
    recompute_user_balances(db, target_id, latest_month)
    db.commit()

    balances = (
        db.query(MonthlyBalance)
        .filter(MonthlyBalance.user_id == target_id)
        .order_by(MonthlyBalance.month.desc())
        .all()
    )
    payments = (
        db.query(Payment)
        .filter(Payment.user_id == target_id)
        .order_by(Payment.created_at.desc())
        .all()
    )
    slips = (
        db.query(PaymentSlip)
        .filter(PaymentSlip.user_id == target_id)
        .order_by(PaymentSlip.uploaded_at.desc())
        .all()
    )

    return {
        "user_id": target_id,
        "balances": [
            {
                "month": b.month,
                "base_amount": str(b.base_amount),
                "old_balance_carried": str(b.old_balance_carried),
                "credit_used": str(b.credit_used),
                "total_due": str(b.total_due),
                "total_paid": str(b.total_paid),
                "outstanding": str(b.outstanding),
                "credit_new": str(b.credit_new),
                "status": b.status.value,
            }
            for b in balances
        ],
        "payments": [
            {
                "id": p.id,
                "month": p.month,
                "amount": str(p.amount),
                "note": p.note,
                "created_at": p.created_at.isoformat(),
            }
            for p in payments
        ],
        "slips": [
            {
                "id": s.id,
                "month": s.month,
                "amount_claimed": str(s.amount_claimed),
                "status": s.status.value,
                "uploaded_at": s.uploaded_at.isoformat(),
                "reject_reason": s.reject_reason,
            }
            for s in slips
        ],
    }
