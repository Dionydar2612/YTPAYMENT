from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import PaymentSlip, SlipStatus, User, UserRole
from app.schemas import SlipOut, SlipRejectRequest
from app.services.calculation import register_payment
from app.services.storage import StorageError, get_storage

router = APIRouter(prefix="/api/slips", tags=["slips"])


@router.post("", response_model=SlipOut, status_code=201)
def upload_slip(
    month: str = Form(...),
    amount_claimed: str = Form(...),
    transferred_at: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        amount = Decimal(amount_claimed)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="จำนวนเงินไม่ถูกต้อง")

    storage = get_storage()
    try:
        rel_path = storage.save(file, subdir=user.id)
    except StorageError as e:
        raise HTTPException(status_code=400, detail=str(e))

    parsed_transferred_at = None
    if transferred_at:
        try:
            parsed_transferred_at = datetime.fromisoformat(transferred_at)
        except ValueError:
            parsed_transferred_at = None

    slip = PaymentSlip(
        user_id=user.id,
        month=month,
        amount_claimed=amount,
        file_path=rel_path,
        transferred_at=parsed_transferred_at,
        status=SlipStatus.pending,
    )
    db.add(slip)
    db.commit()
    db.refresh(slip)
    out = SlipOut.model_validate(slip)
    out.username = user.username
    return out


@router.get("", response_model=List[SlipOut])
def list_slips(
    status_filter: Optional[str] = None,
    mine_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(PaymentSlip)
    if user.role != UserRole.admin or mine_only:
        q = q.filter(PaymentSlip.user_id == user.id)
    if status_filter:
        q = q.filter(PaymentSlip.status == status_filter)
    slips = q.order_by(PaymentSlip.uploaded_at.desc()).all()

    results = []
    for s in slips:
        out = SlipOut.model_validate(s)
        out.username = s.user.username if s.user else None
        results.append(out)
    return results


@router.get("/{slip_id}/file")
def get_slip_file(slip_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    slip = db.get(PaymentSlip, slip_id)
    if not slip:
        raise HTTPException(status_code=404, detail="ไม่พบสลิป")
    if user.role != UserRole.admin and slip.user_id != user.id:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงไฟล์นี้")
    storage = get_storage()
    try:
        path = storage.path_on_disk(slip.file_path)
    except StorageError:
        raise HTTPException(status_code=400, detail="Path ไม่ถูกต้อง")
    return FileResponse(path)


@router.put("/{slip_id}/approve", response_model=SlipOut)
def approve_slip(slip_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    slip = db.get(PaymentSlip, slip_id)
    if not slip:
        raise HTTPException(status_code=404, detail="ไม่พบสลิป")
    if slip.status != SlipStatus.pending:
        raise HTTPException(status_code=400, detail="สลิปนี้ถูกดำเนินการไปแล้ว")

    try:
        slip.status = SlipStatus.approved
        slip.reviewed_by = admin.id
        slip.reviewed_at = datetime.utcnow()

        register_payment(
            db,
            user_id=slip.user_id,
            month=slip.month,
            amount=slip.amount_claimed,
            slip_id=slip.id,
            note=f"อนุมัติสลิป {slip.id}",
            commit=False,
        )

        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(slip)
    out = SlipOut.model_validate(slip)
    out.username = slip.user.username if slip.user else None
    return out


@router.put("/{slip_id}/reject", response_model=SlipOut)
def reject_slip(
    slip_id: str, payload: SlipRejectRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    slip = db.get(PaymentSlip, slip_id)
    if not slip:
        raise HTTPException(status_code=404, detail="ไม่พบสลิป")
    if slip.status != SlipStatus.pending:
        raise HTTPException(status_code=400, detail="สลิปนี้ถูกดำเนินการไปแล้ว")

    slip.status = SlipStatus.rejected
    slip.reviewed_by = admin.id
    slip.reviewed_at = datetime.utcnow()
    slip.reject_reason = payload.reason
    db.commit()
    db.refresh(slip)
    out = SlipOut.model_validate(slip)
    out.username = slip.user.username if slip.user else None
    return out
