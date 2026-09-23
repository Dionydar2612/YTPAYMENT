from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user_optional
from app.models import User, UserRole

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def _redirect_if_needed(user):
    if not user:
        return RedirectResponse(url="/login")
    return None


@router.get("/")
def root(request: Request, user: User = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse(url="/login")
    return RedirectResponse(url="/dashboard")


@router.get("/login")
def login_page(request: Request, user: User = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/dashboard")
def dashboard_page(request: Request, user: User = Depends(get_current_user_optional)):
    r = _redirect_if_needed(user)
    if r:
        return r
    template = "admin_dashboard.html" if user.role == UserRole.admin else "member_dashboard.html"
    return templates.TemplateResponse(template, {"request": request, "user": user})


@router.get("/members")
def members_page(request: Request, user: User = Depends(get_current_user_optional)):
    r = _redirect_if_needed(user)
    if r:
        return r
    if user.role != UserRole.admin:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("members.html", {"request": request, "user": user})


@router.get("/expenses")
def expenses_page(request: Request, user: User = Depends(get_current_user_optional)):
    r = _redirect_if_needed(user)
    if r:
        return r
    if user.role != UserRole.admin:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("expenses.html", {"request": request, "user": user})


@router.get("/slips")
def slips_page(request: Request, user: User = Depends(get_current_user_optional)):
    r = _redirect_if_needed(user)
    if r:
        return r
    return templates.TemplateResponse("slips.html", {"request": request, "user": user})


@router.get("/history")
def history_page(request: Request, user: User = Depends(get_current_user_optional)):
    r = _redirect_if_needed(user)
    if r:
        return r
    return templates.TemplateResponse("history.html", {"request": request, "user": user})


@router.get("/profile")
def profile_page(request: Request, user: User = Depends(get_current_user_optional)):
    r = _redirect_if_needed(user)
    if r:
        return r
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})
