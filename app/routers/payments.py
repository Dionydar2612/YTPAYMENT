from decimal import Decimal
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import (
    get_current_user,
    require_admin,
)
from app.database import get_db
from app.models import (
    Payment,
    User,
    UserRole,
)
from app.services.calculation import (
    register_payment,
    clear_user_outstanding,
    transfer_credit,
)

router = APIRouter(
    prefix="/api/payments",
    tags=["payments"]
)


class ManualPaymentCreate(BaseModel):
    user_id: str
    month: str
    amount: Decimal
    note: Optional[str] = None


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


# =========================================================
# LIST PAYMENTS
# =========================================================

@router.get("")
def list_payments(
    user_id: Optional[str] = None,
    month: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    q = db.query(Payment)

    if user.role != UserRole.admin:

        q = q.filter(
            Payment.user_id == user.id
        )

    elif user_id:

        q = q.filter(
            Payment.user_id == user_id
        )

    if month:

        q = q.filter(
            Payment.month == month
        )

    payments = (
        q.order_by(
            Payment.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "username": (
                p.user.username
                if p.user
                else None
            ),
            "month": p.month,
            "amount": str(p.amount),
            "note": p.note,
            "created_at": (
                p.created_at.isoformat()
            ),
        }
        for p in payments
    ]


# =========================================================
# MANUAL PAYMENT
# =========================================================

@router.post(
    "",
    status_code=201
)
def manual_payment(
    payload: ManualPaymentCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):

    target = db.get(
        User,
        payload.user_id
    )

    if not target:
        raise HTTPException(
            status_code=404,
            detail="ไม่พบสมาชิก"
        )

    amount = payload.amount.quantize(
        Decimal("0.01")
    )

    if amount == 0:
        raise HTTPException(
            status_code=400,
            detail="จำนวนเงินต้องไม่เป็น 0"
        )

    try:

        payment = register_payment(
            db,
            user_id=payload.user_id,
            month=payload.month,
            amount=amount,
            note=(
                payload.note
                or "เพิ่มยอดชำระโดย Admin"
            ),
        )

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    return {
        "ok": True,
        "payment_id": payment.id,
        "month": payment.month,
        "amount": str(payment.amount),
    }


# =========================================================
# CLEAR OUTSTANDING
# =========================================================

@router.post(
    "/clear/{user_id}"
)
def clear_outstanding(
    user_id: str,
    payload: ClearOutstandingRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):

    user = db.get(
        User,
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="ไม่พบสมาชิก"
        )

    try:

        result = clear_user_outstanding(
            db,
            user_id=user_id,
            amount=payload.amount,
            note=(
                payload.note
                or "เคลียร์ยอดค้างโดย Admin"
            ),
        )

        return {
            "ok": True,
            **result,
        }

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# =========================================================
# TRANSFER CREDIT
# =========================================================

@router.post(
    "/credit-transfer"
)
def credit_transfer(
    payload: CreditTransferRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):

    try:

        transfer = transfer_credit(
            db,
            from_user_id=payload.from_user_id,
            source_month=payload.source_month,
            to_user_id=payload.to_user_id,
            target_month=payload.target_month,
            amount=payload.amount,
            note=payload.note,
            created_by=admin.id,
        )

        return {
            "ok": True,
            "transfer_id": transfer.id,
            "amount": str(
                transfer.amount
            ),
            "source": {
                "user_id": transfer.source_user_id,
                "month": transfer.source_month,
            },
            "target": {
                "user_id": transfer.target_user_id,
                "month": transfer.target_month,
            },
        }

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
