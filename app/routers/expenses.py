from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_admin, get_current_user
from app.database import get_db
from app.models import Expense, User
from app.schemas import ExpenseCreate, ExpenseOut
from app.services.calculation import create_expense

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


@router.get("", response_model=List[ExpenseOut])
def list_expenses(
    month: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Expense).order_by(Expense.month.desc(), Expense.created_at.desc())
    if month:
        q = q.filter(Expense.month == month)
    return q.all()


@router.post("", response_model=ExpenseOut, status_code=201)
def add_expense(payload: ExpenseCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        expense = create_expense(
            db,
            month=payload.month,
            description=payload.description,
            total_amount=payload.total_amount,
            created_by=admin.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return expense
