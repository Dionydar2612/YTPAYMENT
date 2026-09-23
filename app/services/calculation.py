"""
ระบบคำนวณยอดเงินแบบแยกเดือน

หลักการ:

1. แต่ละเดือนคิดยอดของตัวเอง
2. ยอดค้างเดือนเก่าไม่ถูกย้ายไปเพิ่มในเดือนใหม่
3. เครดิตไม่ถูกนำไปใช้เอง
4. เครดิตเกิดจากการจ่ายเกินในเดือนนั้น
5. Admin สามารถนำเครดิตไปจัดสรรให้เดือนอื่นด้วยมือ
6. การ "เคลียร์ยอด" จะสร้าง Payment ไปตัดเดือนที่ค้างเก่าสุดก่อน
"""

from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import (
    User,
    Expense,
    ExpenseParticipant,
    MonthlyBalance,
    Payment,
    BalanceStatus,
    CreditAllocation,
)


TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")


# =========================================================
# HELPERS
# =========================================================

def _q(value) -> Decimal:
    """
    แปลงค่าเป็น Decimal 2 ตำแหน่ง
    """
    return Decimal(value or ZERO).quantize(TWOPLACES)


def _validate_month(month: str):
    """
    ตรวจสอบรูปแบบเดือน YYYY-MM
    """

    try:
        if len(month) != 7 or month[4] != "-":
            raise ValueError

        year = int(month[:4])
        mon = int(month[5:])

        if year < 1 or not 1 <= mon <= 12:
            raise ValueError

    except (TypeError, ValueError):
        raise ValueError(
            "เดือนต้องอยู่ในรูปแบบ YYYY-MM"
        )


def _next_month(month: str) -> str:
    """
    หาเดือนถัดไป
    """

    _validate_month(month)

    year = int(month[:4])
    mon = int(month[5:])

    if mon == 12:
        return f"{year + 1:04d}-01"

    return f"{year:04d}-{mon + 1:02d}"


def _month_range(start: str, end: str):
    """
    วนเดือนตั้งแต่ start ถึง end
    """

    _validate_month(start)
    _validate_month(end)

    current = start

    while current <= end:
        yield current

        if current == end:
            break

        current = _next_month(current)


def current_month() -> str:
    """
    คืนค่าเดือนปัจจุบันในรูปแบบ YYYY-MM
    """

    return datetime.now().strftime("%Y-%m")


def _last_known_month(
    db: Session,
    user_id: Optional[str] = None,
    fallback: Optional[str] = None,
) -> str:
    """คืนเดือนล่าสุดที่ระบบรู้จักสำหรับสมาชิก/ระบบ

    รองรับการเรียกทั้งแบบ:
        _last_known_month(db, user_id)
        _last_known_month(db, user_id, "1900-01")

    จะตรวจจาก balances, payments, expenses และ credit allocations
    เพื่อให้หน้า history/member detail ครอบคลุมเดือนที่มีข้อมูลจริง
    """
    months = []

    balance_q = db.query(MonthlyBalance.month)
    if user_id:
        balance_q = balance_q.filter(MonthlyBalance.user_id == user_id)
    months.extend(row[0] for row in balance_q.all() if row[0])

    payment_q = db.query(Payment.month)
    if user_id:
        payment_q = payment_q.filter(Payment.user_id == user_id)
    months.extend(row[0] for row in payment_q.all() if row[0])

    expense_q = (
        db.query(Expense.month)
        .join(ExpenseParticipant, ExpenseParticipant.expense_id == Expense.id)
    )
    if user_id:
        expense_q = expense_q.filter(ExpenseParticipant.user_id == user_id)
    months.extend(row[0] for row in expense_q.all() if row[0])

    allocation_q = db.query(
        CreditAllocation.source_month,
        CreditAllocation.target_month,
    )
    if user_id:
        allocation_q = allocation_q.filter(
            (CreditAllocation.source_user_id == user_id)
            | (CreditAllocation.target_user_id == user_id)
        )
    for source_month, target_month in allocation_q.all():
        if source_month:
            months.append(source_month)
        if target_month:
            months.append(target_month)

    if months:
        return max(months)

    if fallback:
        _validate_month(fallback)
        return fallback

    return current_month()


# =========================================================
# PARTICIPANTS
# =========================================================

def get_active_participants(
    db: Session,
) -> List[User]:

    return (
        db.query(User)
        .filter(User.is_active == True)
        .order_by(
            User.role.asc(),
            User.username.asc(),
        )
        .all()
    )


def split_amount(
    total_amount: Decimal,
    participants: List[User],
) -> dict:

    total_amount = _q(total_amount)

    if total_amount <= ZERO:
        raise ValueError(
            "จำนวนเงินต้องมากกว่า 0"
        )

    if not participants:
        raise ValueError(
            "ไม่มีผู้ร่วมจ่าย"
        )

    total_cents = int(
        (
            total_amount * 100
        ).to_integral_value(
            rounding=ROUND_DOWN
        )
    )

    base_cents, remainder = divmod(
        total_cents,
        len(participants),
    )

    result = {}

    for index, user in enumerate(participants):

        cents = (
            base_cents
            + (1 if index < remainder else 0)
        )

        result[user.id] = _q(
            Decimal(cents) / 100
        )

    return result


# =========================================================
# EXPENSE
# =========================================================

def create_expense(
    db: Session,
    month: str,
    description: str,
    total_amount: Decimal,
    created_by: Optional[str],
) -> Expense:

    _validate_month(month)

    total_amount = _q(total_amount)

    if total_amount <= ZERO:
        raise ValueError(
            "จำนวนเงินต้องมากกว่า 0"
        )

    participants = get_active_participants(db)

    if not participants:
        raise ValueError(
            "ไม่มีสมาชิกที่ Active สำหรับคำนวณ"
        )

    amounts = split_amount(
        total_amount,
        participants,
    )

    per_person_amount = _q(
        total_amount / len(participants)
    )

    expense = Expense(
        month=month,
        description=description.strip(),
        total_amount=total_amount,
        participants_count=len(participants),
        per_person_amount=per_person_amount,
        created_by=created_by,
    )

    db.add(expense)
    db.flush()

    for user in participants:

        db.add(
            ExpenseParticipant(
                expense_id=expense.id,
                user_id=user.id,
                amount=amounts[user.id],
            )
        )

    db.flush()

    # คำนวณเฉพาะเดือนนี้
    for user in participants:

        recompute_user_balances(
            db,
            user.id,
            month,
        )

    db.commit()
    db.refresh(expense)

    return expense


# =========================================================
# BALANCE
# =========================================================

def get_or_create_balance(
    db: Session,
    user_id: str,
    month: str,
) -> MonthlyBalance:

    _validate_month(month)

    balance = (
        db.query(MonthlyBalance)
        .filter(
            MonthlyBalance.user_id == user_id,
            MonthlyBalance.month == month,
        )
        .first()
    )

    if balance:
        return balance

    balance = MonthlyBalance(
        user_id=user_id,
        month=month,
        base_amount=ZERO,
        old_balance_carried=ZERO,
        credit_used=ZERO,
        credit_source_month=None,
        total_due=ZERO,
        total_paid=ZERO,
        outstanding=ZERO,
        credit_new=ZERO,
        status=BalanceStatus.unpaid,
    )

    db.add(balance)
    db.flush()

    return balance


def _base_amount(
    db: Session,
    user_id: str,
    month: str,
) -> Decimal:

    rows = (
        db.query(
            ExpenseParticipant.amount
        )
        .join(
            Expense,
            Expense.id == ExpenseParticipant.expense_id,
        )
        .filter(
            ExpenseParticipant.user_id == user_id,
            Expense.month == month,
        )
        .all()
    )

    return _q(
        sum(
            (
                Decimal(row[0])
                for row in rows
            ),
            ZERO,
        )
    )


def _paid_amount(
    db: Session,
    user_id: str,
    month: str,
) -> Decimal:

    rows = (
        db.query(Payment.amount)
        .filter(
            Payment.user_id == user_id,
            Payment.month == month,
        )
        .all()
    )

    return _q(
        sum(
            (
                Decimal(row[0])
                for row in rows
            ),
            ZERO,
        )
    )


# =========================================================
# CREDIT RECEIVED
# =========================================================

def _credit_received(
    db: Session,
    user_id: str,
    month: str,
) -> Decimal:

    rows = (
        db.query(
            CreditAllocation.amount
        )
        .filter(
            CreditAllocation.target_user_id == user_id,
            CreditAllocation.target_month == month,
        )
        .all()
    )

    return _q(
        sum(
            (
                Decimal(row[0])
                for row in rows
            ),
            ZERO,
        )
    )


# =========================================================
# CREDIT GENERATED
# =========================================================

def _credit_generated_before_transfer(
    db: Session,
    user_id: str,
    month: str,
) -> Decimal:

    """
    เครดิตที่เกิดจริงจากการจ่ายเกินในเดือนนั้น
    ก่อนหักเครดิตที่ Admin เอาไปจัดสรร
    """

    base = _base_amount(
        db,
        user_id,
        month,
    )

    balance = get_or_create_balance(
        db,
        user_id,
        month,
    )

    old_balance = _q(
        balance.old_balance_carried
    )

    paid = _paid_amount(
        db,
        user_id,
        month,
    )

    due = _q(
        base + old_balance
    )

    credit = paid - due

    if credit < ZERO:
        return ZERO

    return _q(credit)


# =========================================================
# CREDIT TRANSFERRED OUT
# =========================================================

def _credit_transferred_out(
    db: Session,
    user_id: str,
    source_month: str,
) -> Decimal:

    rows = (
        db.query(
            CreditAllocation.amount
        )
        .filter(
            CreditAllocation.source_user_id == user_id,
            CreditAllocation.source_month == source_month,
        )
        .all()
    )

    return _q(
        sum(
            (
                Decimal(row[0])
                for row in rows
            ),
            ZERO,
        )
    )


# =========================================================
# AVAILABLE CREDIT
# =========================================================

def available_credit(
    db: Session,
    user_id: str,
    source_month: str,
) -> Decimal:

    generated = _credit_generated_before_transfer(
        db,
        user_id,
        source_month,
    )

    transferred = _credit_transferred_out(
        db,
        user_id,
        source_month,
    )

    result = generated - transferred

    if result < ZERO:
        return ZERO

    return _q(result)


# =========================================================
# RECOMPUTE BALANCE
# =========================================================

def recompute_user_balances(
    db: Session,
    user_id: str,
    through_month: str,
) -> MonthlyBalance:

    """
    คำนวณยอดของสมาชิกในเดือนที่ระบุ

    ไม่มีการ carry outstanding
    ไปเดือนถัดไปโดยอัตโนมัติ

    ตัวอย่าง:

    2026-08
    ต้องจ่าย 79.80
    จ่าย 0
    ค้าง 79.80

    2026-09
    ต้องจ่าย 79.80
    จ่าย 0
    ค้าง 79.80

    ไม่ใช่:

    2026-09 ต้องจ่าย 159.60
    """

    _validate_month(through_month)

    balance = get_or_create_balance(
        db,
        user_id,
        through_month,
    )

    base = _base_amount(
        db,
        user_id,
        through_month,
    )

    old_balance = _q(
        balance.old_balance_carried
    )

    paid = _paid_amount(
        db,
        user_id,
        through_month,
    )

    credit_received = _credit_received(
        db,
        user_id,
        through_month,
    )

    total_due = _q(
        base + old_balance
    )

    # เครดิตช่วยลดเฉพาะยอดของเดือนนี้
    amount_after_credit = _q(
        total_due - credit_received
    )

    if amount_after_credit < ZERO:
        amount_after_credit = ZERO

    # -----------------------------------------------------
    # Paid >= Due
    # -----------------------------------------------------

    if paid >= amount_after_credit:

        outstanding = ZERO

        generated_credit = _q(
            paid - amount_after_credit
        )

        status = (
            BalanceStatus.credit
            if generated_credit > ZERO
            else BalanceStatus.paid
        )

    # -----------------------------------------------------
    # Paid < Due
    # -----------------------------------------------------

    else:

        outstanding = _q(
            amount_after_credit - paid
        )

        generated_credit = ZERO

        status = (
            BalanceStatus.partial
            if paid > ZERO
            else BalanceStatus.unpaid
        )

    # -----------------------------------------------------
    # หักเครดิตที่ Admin โอนออก
    # -----------------------------------------------------

    transferred_out = _credit_transferred_out(
        db,
        user_id,
        through_month,
    )

    credit_available = _q(
        generated_credit - transferred_out
    )

    if credit_available < ZERO:
        credit_available = ZERO

    # -----------------------------------------------------
    # Update balance
    # -----------------------------------------------------

    balance.base_amount = base

    balance.credit_used = credit_received

    balance.credit_source_month = None

    balance.total_due = total_due

    balance.total_paid = paid

    balance.outstanding = outstanding

    balance.credit_new = credit_available

    balance.status = (
        BalanceStatus.credit
        if credit_available > ZERO
        else status
    )

    balance.updated_at = datetime.utcnow()

    db.flush()

    return balance


# =========================================================
# OLD BALANCE
# =========================================================

def add_old_balance(
    db: Session,
    user_id: str,
    month: str,
    amount: Decimal,
):

    _validate_month(month)

    amount = _q(amount)

    if amount <= ZERO:
        raise ValueError(
            "ยอดค้างเก่าต้องมากกว่า 0"
        )

    balance = get_or_create_balance(
        db,
        user_id,
        month,
    )

    balance.old_balance_carried = _q(
        balance.old_balance_carried + amount
    )

    recompute_user_balances(
        db,
        user_id,
        month,
    )

    db.commit()

    return balance


# =========================================================
# PAYMENT
# =========================================================

def register_payment(
    db: Session,
    user_id: str,
    month: str,
    amount: Decimal,
    slip_id: Optional[str] = None,
    note: Optional[str] = None,
    commit: bool = True,
):

    _validate_month(month)

    amount = _q(amount)

    if amount <= ZERO:
        raise ValueError(
            "จำนวนเงินต้องมากกว่า 0"
        )

    payment = Payment(
        user_id=user_id,
        month=month,
        amount=amount,
        slip_id=slip_id,
        note=note,
    )

    db.add(payment)
    db.flush()

    recompute_user_balances(
        db,
        user_id,
        month,
    )

    if commit:

        db.commit()
        db.refresh(payment)

    return payment


# =========================================================
# CLEAR OUTSTANDING
# =========================================================

def get_user_outstanding_months(
    db: Session,
    user_id: str,
):

    balances = (
        db.query(MonthlyBalance)
        .filter(
            MonthlyBalance.user_id == user_id,
            MonthlyBalance.outstanding > 0,
        )
        .order_by(
            MonthlyBalance.month.asc()
        )
        .all()
    )

    for balance in balances:

        recompute_user_balances(
            db,
            user_id,
            balance.month,
        )

    db.flush()

    return (
        db.query(MonthlyBalance)
        .filter(
            MonthlyBalance.user_id == user_id,
            MonthlyBalance.outstanding > 0,
        )
        .order_by(
            MonthlyBalance.month.asc()
        )
        .all()
    )


def clear_user_outstanding(
    db: Session,
    user_id: str,
    amount: Optional[Decimal],
    note: str = "เคลียร์ยอดค้างโดย Admin",
):

    outstanding_rows = get_user_outstanding_months(
        db,
        user_id,
    )

    total_outstanding = _q(
        sum(
            (
                Decimal(row.outstanding)
                for row in outstanding_rows
            ),
            ZERO,
        )
    )

    if total_outstanding <= ZERO:
        raise ValueError(
            "สมาชิกคนนี้ไม่มียอดค้าง"
        )

    if amount is None:
        amount = total_outstanding

    amount = _q(amount)

    if amount <= ZERO:
        raise ValueError(
            "จำนวนเงินต้องมากกว่า 0"
        )

    if amount > total_outstanding:
        raise ValueError(
            f"จำนวนเงินมากกว่ายอดค้าง "
            f"ยอดค้างทั้งหมด {total_outstanding:.2f} บาท"
        )

    remaining = amount
    payments = []

    # -----------------------------------------------------
    # ตัดยอดจากเดือนเก่าสุดก่อน
    # -----------------------------------------------------

    for balance in outstanding_rows:

        if remaining <= ZERO:
            break

        outstanding = _q(
            balance.outstanding
        )

        pay_amount = min(
            remaining,
            outstanding,
        )

        payment = Payment(
            user_id=user_id,
            month=balance.month,
            amount=pay_amount,
            note=note,
        )

        db.add(payment)

        payments.append(payment)

        remaining = _q(
            remaining - pay_amount
        )

    db.flush()

    # -----------------------------------------------------
    # Recompute เดือนที่เกี่ยวข้อง
    # -----------------------------------------------------

    for payment in payments:

        recompute_user_balances(
            db,
            user_id,
            payment.month,
        )

    db.commit()

    return {
        "amount": str(amount),

        "remaining_outstanding": str(
            total_outstanding - amount
        ),

        "payments": [
            {
                "month": payment.month,
                "amount": str(payment.amount),
            }
            for payment in payments
        ],
    }


# =========================================================
# CREDIT ALLOCATION
# =========================================================

def transfer_credit(
    db: Session,
    from_user_id: str,
    source_month: str,
    to_user_id: str,
    target_month: str,
    amount: Decimal,
    note: Optional[str] = None,
    created_by: Optional[str] = None,
):

    """
    Admin โอนเครดิตจากสมาชิก/เดือนหนึ่ง
    ไปยังสมาชิก/เดือนหนึ่ง
    """

    _validate_month(source_month)
    _validate_month(target_month)

    amount = _q(amount)

    if amount <= ZERO:
        raise ValueError(
            "จำนวนเครดิตต้องมากกว่า 0"
        )

    if (
        from_user_id == to_user_id
        and source_month == target_month
    ):
        raise ValueError(
            "ไม่สามารถโอนเครดิตให้ตัวเองในเดือนเดียวกัน"
        )

    # -----------------------------------------------------
    # ตรวจสอบสมาชิกต้นทาง
    # -----------------------------------------------------

    source_user = db.get(
        User,
        from_user_id,
    )

    if not source_user:
        raise ValueError(
            "ไม่พบสมาชิกต้นทาง"
        )

    # -----------------------------------------------------
    # ตรวจสอบสมาชิกปลายทาง
    # -----------------------------------------------------

    target_user = db.get(
        User,
        to_user_id,
    )

    if not target_user:
        raise ValueError(
            "ไม่พบสมาชิกปลายทาง"
        )

    # -----------------------------------------------------
    # ตรวจสอบเครดิตต้นทาง
    # -----------------------------------------------------

    available = available_credit(
        db,
        from_user_id,
        source_month,
    )

    if amount > available:
        raise ValueError(
            f"เครดิตไม่พอ "
            f"เครดิตที่ใช้ได้ {available:.2f} บาท"
        )

    # -----------------------------------------------------
    # ตรวจสอบยอดปลายทาง
    # -----------------------------------------------------

    target_balance = recompute_user_balances(
        db,
        to_user_id,
        target_month,
    )

    target_outstanding = _q(
        target_balance.outstanding
    )

    if amount > target_outstanding:
        raise ValueError(
            f"ยอดค้างของปลายทางมีเพียง "
            f"{target_outstanding:.2f} บาท"
        )

    # -----------------------------------------------------
    # สร้าง CreditAllocation
    # -----------------------------------------------------

    allocation = CreditAllocation(
        source_user_id=from_user_id,
        source_month=source_month,

        target_user_id=to_user_id,
        target_month=target_month,

        amount=amount,
        note=note,
        created_by=created_by,
    )

    db.add(allocation)
    db.flush()

    # -----------------------------------------------------
    # Recompute ต้นทาง
    # -----------------------------------------------------

    recompute_user_balances(
        db,
        from_user_id,
        source_month,
    )

    # -----------------------------------------------------
    # Recompute ปลายทาง
    # -----------------------------------------------------

    recompute_user_balances(
        db,
        to_user_id,
        target_month,
    )

    db.commit()
    db.refresh(allocation)

    return allocation
