from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    CreditAllocation,
    Expense,
    ExpenseParticipant,
    MonthlyBalance,
    Payment,
    PaymentSlip,
    User,
    UserRole,
)
from app.services.calculation import (
    recompute_user_balances,
)


router = APIRouter(
    prefix="/api/history",
    tags=["history"],
)


ZERO = Decimal("0.00")


# ============================================================
# ตรวจว่า MonthlyBalance มีข้อมูลจริงหรือไม่
# ============================================================

def has_real_balance_data(
    balance: MonthlyBalance,
) -> bool:

    values = [
        balance.base_amount,
        balance.old_balance_carried,
        balance.credit_used,
        balance.total_due,
        balance.total_paid,
        balance.outstanding,
        balance.credit_new,
    ]

    return any(
        value is not None
        and Decimal(str(value)) != ZERO
        for value in values
    )


# ============================================================
# หาเดือนที่มีข้อมูลจริง
# ============================================================

def get_real_months(
    db: Session,
    user_id: str,
):

    months = set()

    # --------------------------------------------------------
    # MonthlyBalance
    # --------------------------------------------------------

    balances = (
        db.query(MonthlyBalance)
        .filter(
            MonthlyBalance.user_id == user_id
        )
        .all()
    )

    for balance in balances:

        if has_real_balance_data(
            balance
        ):
            months.add(
                balance.month
            )

    # --------------------------------------------------------
    # Payment
    # --------------------------------------------------------

    payment_months = (
        db.query(Payment.month)
        .filter(
            Payment.user_id == user_id
        )
        .distinct()
        .all()
    )

    for row in payment_months:

        if row[0]:
            months.add(
                row[0]
            )

    # --------------------------------------------------------
    # Payment Slip
    # --------------------------------------------------------

    slip_months = (
        db.query(PaymentSlip.month)
        .filter(
            PaymentSlip.user_id == user_id
        )
        .distinct()
        .all()
    )

    for row in slip_months:

        if row[0]:
            months.add(
                row[0]
            )

    # --------------------------------------------------------
    # Expense
    # --------------------------------------------------------

    expense_months = (
        db.query(Expense.month)
        .join(
            ExpenseParticipant,
            ExpenseParticipant.expense_id
            == Expense.id,
        )
        .filter(
            ExpenseParticipant.user_id == user_id
        )
        .distinct()
        .all()
    )

    for row in expense_months:

        if row[0]:
            months.add(
                row[0]
            )

    # --------------------------------------------------------
    # Credit received
    # --------------------------------------------------------

    credit_received_months = (
        db.query(
            CreditAllocation.target_month
        )
        .filter(
            CreditAllocation.target_user_id
            == user_id
        )
        .distinct()
        .all()
    )

    for row in credit_received_months:

        if row[0]:
            months.add(
                row[0]
            )

    # --------------------------------------------------------
    # Credit sent
    # --------------------------------------------------------

    credit_sent_months = (
        db.query(
            CreditAllocation.source_month
        )
        .filter(
            CreditAllocation.source_user_id
            == user_id
        )
        .distinct()
        .all()
    )

    for row in credit_sent_months:

        if row[0]:
            months.add(
                row[0]
            )

    return sorted(
        months,
        reverse=True,
    )


# ============================================================
# History
# ============================================================

@router.get("")
def get_history(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    # --------------------------------------------------------
    # กำหนด user ที่ต้องการดู
    # --------------------------------------------------------

    target_id = user.id

    if (
        user_id
        and user.role == UserRole.admin
    ):
        target_id = user_id

    elif (
        user_id
        and user_id != user.id
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "ไม่สามารถดูประวัติของสมาชิกคนอื่นได้"
            ),
        )

    # --------------------------------------------------------
    # หาเฉพาะเดือนที่มีข้อมูลจริง
    #
    # สำคัญ:
    # ไม่มี current_month()
    # ไม่มี _last_known_month()
    # ไม่มีการสร้างเดือนใหม่
    # --------------------------------------------------------

    real_months = get_real_months(
        db,
        target_id,
    )

    # --------------------------------------------------------
    # Recompute เฉพาะเดือนที่มีข้อมูล
    # --------------------------------------------------------

    for month in real_months:

        recompute_user_balances(
            db,
            target_id,
            month,
        )

    db.commit()

    # --------------------------------------------------------
    # โหลด balances
    # --------------------------------------------------------

    if real_months:

        balances = (
            db.query(MonthlyBalance)
            .filter(
                MonthlyBalance.user_id
                == target_id,

                MonthlyBalance.month.in_(
                    real_months
                ),
            )
            .order_by(
                MonthlyBalance.month.desc()
            )
            .all()
        )

    else:

        balances = []

    # --------------------------------------------------------
    # Payments
    # --------------------------------------------------------

    payments = (
        db.query(Payment)
        .filter(
            Payment.user_id == target_id
        )
        .order_by(
            Payment.created_at.desc()
        )
        .all()
    )

    # --------------------------------------------------------
    # Slips
    # --------------------------------------------------------

    slips = (
        db.query(PaymentSlip)
        .filter(
            PaymentSlip.user_id == target_id
        )
        .order_by(
            PaymentSlip.uploaded_at.desc()
        )
        .all()
    )

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "user_id": target_id,

        "balances": [
            {
                "month": b.month,

                "base_amount":
                    str(b.base_amount),

                "old_balance_carried":
                    str(
                        b.old_balance_carried
                    ),

                "credit_used":
                    str(
                        b.credit_used
                    ),

                "total_due":
                    str(
                        b.total_due
                    ),

                "total_paid":
                    str(
                        b.total_paid
                    ),

                "outstanding":
                    str(
                        b.outstanding
                    ),

                "credit_new":
                    str(
                        b.credit_new
                    ),

                "status":
                    b.status.value,
            }

            for b in balances
        ],

        "payments": [
            {
                "id": p.id,
                "month": p.month,
                "amount": str(p.amount),
                "note": p.note,
                "created_at":
                    p.created_at.isoformat(),
            }

            for p in payments
        ],

        "slips": [
            {
                "id": s.id,
                "month": s.month,
                "amount_claimed":
                    str(s.amount_claimed),

                "status":
                    s.status.value,

                "uploaded_at":
                    s.uploaded_at.isoformat(),

                "reject_reason":
                    s.reject_reason,
            }

            for s in slips
        ],
    }
