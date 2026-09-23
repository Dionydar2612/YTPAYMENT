import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Enum,
    Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ============================================================
# Helpers
# ============================================================

def gen_uuid() -> str:
    """Generate UUID string for primary keys."""
    return str(uuid.uuid4())


# ============================================================
# Enums
# ============================================================

class UserRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class SlipStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class BalanceStatus(str, enum.Enum):
    unpaid = "unpaid"
    partial = "partial"
    paid = "paid"
    credit = "credit"


# ============================================================
# User
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(
        String(36),
        primary_key=True,
        default=gen_uuid,
    )

    username = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = Column(
        String(255),
        nullable=False,
    )

    full_name = Column(
        String(128),
        nullable=True,
    )

    role = Column(
        Enum(UserRole),
        nullable=False,
        default=UserRole.member,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    slips = relationship(
        "PaymentSlip",
        back_populates="user",
        foreign_keys="PaymentSlip.user_id",
    )

    balances = relationship(
        "MonthlyBalance",
        back_populates="user",
    )


# ============================================================
# Expense
# ============================================================

class Expense(Base):
    """
    รายการค่าใช้จ่ายของแต่ละเดือน

    participants_count และ per_person_amount
    จะถูก snapshot ตอนสร้าง Expense
    เพื่อไม่ให้ยอดย้อนหลังเปลี่ยนตามจำนวนสมาชิกในอนาคต
    """

    __tablename__ = "expenses"

    id = Column(
        String(36),
        primary_key=True,
        default=gen_uuid,
    )

    month = Column(
        String(7),
        nullable=False,
    )

    description = Column(
        String(255),
        nullable=False,
    )

    total_amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    participants_count = Column(
        Integer,
        nullable=False,
    )

    per_person_amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    created_by = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    participants = relationship(
        "ExpenseParticipant",
        back_populates="expense",
        cascade="all, delete-orphan",
    )

    # --------------------------------------------------------
    # Indexes
    # --------------------------------------------------------

    __table_args__ = (
        Index(
            "ix_expenses_month",
            "month",
        ),
    )


# ============================================================
# Expense Participant
# ============================================================

class ExpenseParticipant(Base):
    """
    ระบุว่าสมาชิกคนไหนถูกคิดค่าใช้จ่ายรายการนั้น
    และแต่ละคนต้องรับผิดชอบจำนวนเท่าไร
    """

    __tablename__ = "expense_participants"

    id = Column(
        String(36),
        primary_key=True,
        default=gen_uuid,
    )

    expense_id = Column(
        String(36),
        ForeignKey("expenses.id"),
        nullable=False,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )

    amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    expense = relationship(
        "Expense",
        back_populates="participants",
    )

    user = relationship(
        "User",
    )

    # --------------------------------------------------------
    # Constraints / Indexes
    # --------------------------------------------------------

    __table_args__ = (
        UniqueConstraint(
            "expense_id",
            "user_id",
            name="uq_expense_user",
        ),

        Index(
            "ix_expense_participants_user",
            "user_id",
        ),
    )


# ============================================================
# Monthly Balance
# ============================================================

class MonthlyBalance(Base):
    """
    ยอดของสมาชิกแต่ละคนในแต่ละเดือน

    base_amount:
        ยอดค่าใช้จ่ายพื้นฐานของเดือนนั้น

    old_balance_carried:
        ยอดค้างเก่าที่ Admin เพิ่มด้วยมือ

    credit_used:
        เครดิตจากเดือนก่อนที่นำมาใช้

    credit_source_month:
        เดือนต้นทางของเครดิต

    total_due:
        ยอดที่ต้องจ่ายทั้งหมด

    total_paid:
        ยอดที่จ่ายแล้ว

    outstanding:
        ยอดค้างชำระ

    credit_new:
        เครดิตที่เหลือและสามารถนำไปเดือนถัดไป
    """

    __tablename__ = "monthly_balances"

    id = Column(
        String(36),
        primary_key=True,
        default=gen_uuid,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )

    month = Column(
        String(7),
        nullable=False,
    )

    # --------------------------------------------------------
    # Amounts
    # --------------------------------------------------------

    base_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    old_balance_carried = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    credit_used = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    credit_source_month = Column(
        String(7),
        nullable=True,
    )

    total_due = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    total_paid = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    outstanding = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    credit_new = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    status = Column(
        Enum(BalanceStatus),
        nullable=False,
        default=BalanceStatus.unpaid,
    )

    # --------------------------------------------------------
    # Timestamps
    # --------------------------------------------------------

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    user = relationship(
        "User",
        back_populates="balances",
    )

    # --------------------------------------------------------
    # Constraints / Indexes
    # --------------------------------------------------------

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "month",
            name="uq_user_month",
        ),

        Index(
            "ix_monthly_balances_month",
            "month",
        ),
    )


# ============================================================
# Payment Slip
# ============================================================

class PaymentSlip(Base):
    """
    สลิปที่สมาชิกอัปโหลดเข้ามา
    รอ Admin ตรวจสอบและอนุมัติ
    """

    __tablename__ = "payment_slips"

    id = Column(
        String(36),
        primary_key=True,
        default=gen_uuid,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )

    month = Column(
        String(7),
        nullable=False,
        index=True,
    )

    amount_claimed = Column(
        Numeric(12, 2),
        nullable=False,
    )

    file_path = Column(
        String(500),
        nullable=False,
    )

    transferred_at = Column(
        DateTime,
        nullable=True,
    )

    status = Column(
        Enum(SlipStatus),
        nullable=False,
        default=SlipStatus.pending,
    )

    reviewed_by = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
    )

    reviewed_at = Column(
        DateTime,
        nullable=True,
    )

    reject_reason = Column(
        Text,
        nullable=True,
    )

    uploaded_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    user = relationship(
        "User",
        back_populates="slips",
        foreign_keys=[user_id],
    )


# ============================================================
# Payment
# ============================================================

class Payment(Base):
    """
    รายการชำระเงินจริงที่ได้รับการยืนยันแล้ว

    โดยปกติจะถูกสร้างเมื่อ Admin
    อนุมัติ PaymentSlip
    """

    __tablename__ = "payments"

    id = Column(
        String(36),
        primary_key=True,
        default=gen_uuid,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )

    month = Column(
        String(7),
        nullable=False,
        index=True,
    )

    amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    slip_id = Column(
        String(36),
        ForeignKey("payment_slips.id"),
        nullable=True,
    )

    note = Column(
        String(255),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    user = relationship(
        "User",
    )

    slip = relationship(
        "PaymentSlip",
    )

    # --------------------------------------------------------
    # Indexes
    # --------------------------------------------------------

    __table_args__ = (
        Index(
            "ix_payments_user_month",
            "user_id",
            "month",
        ),
    )


# ============================================================
# Credit Allocation
# ============================================================

class CreditAllocation(Base):
    """
    การโอนเครดิตด้วยมือโดย Admin

    ตัวอย่าง:

        สมาชิก A / 2026-09
                |
                | 100 บาท
                v
        สมาชิก B / 2026-10

    source_user_id:
        สมาชิกต้นทาง

    source_month:
        เดือนต้นทาง

    target_user_id:
        สมาชิกปลายทาง

    target_month:
        เดือนปลายทาง

    amount:
        จำนวนเครดิตที่โอน

    note:
        หมายเหตุของ Admin

    created_by:
        Admin ที่ทำรายการ
    """

    __tablename__ = "credit_allocations"

    id = Column(
        String(36),
        primary_key=True,
        default=gen_uuid,
    )

    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    source_user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )

    source_month = Column(
        String(7),
        nullable=False,
    )

    # --------------------------------------------------------
    # Target
    # --------------------------------------------------------

    target_user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )

    target_month = Column(
        String(7),
        nullable=False,
    )

    # --------------------------------------------------------
    # Amount
    # --------------------------------------------------------

    amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    # --------------------------------------------------------
    # Additional information
    # --------------------------------------------------------

    note = Column(
        String(255),
        nullable=True,
    )

    created_by = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    source_user = relationship(
        "User",
        foreign_keys=[source_user_id],
    )

    target_user = relationship(
        "User",
        foreign_keys=[target_user_id],
    )

    admin = relationship(
        "User",
        foreign_keys=[created_by],
    )

    # --------------------------------------------------------
    # Indexes
    # --------------------------------------------------------

    __table_args__ = (
        Index(
            "ix_credit_alloc_source",
            "source_user_id",
            "source_month",
        ),

        Index(
            "ix_credit_alloc_target",
            "target_user_id",
            "target_month",
        ),
    )
