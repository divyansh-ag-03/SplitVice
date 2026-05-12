"""
Server-rendered web routes.

All routes return HTML (full pages or redirects).
No business logic here — call services, render templates.
Auth is cookie-based via get_current_web_user().
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.expenses import CreateExpenseRequest, ExpenseSplitRequest
from app.schemas.groups import AddMemberRequest, CreateGroupRequest
from app.schemas.settlements import CreateSettlementRequest
from app.schemas.users import UserPublic
from app.services import auth_service, balance_service, expense_service, group_service, settlement_service
from app.web.cookies import clear_auth_cookie, set_auth_cookie
from app.web.dependencies import get_current_web_user
from app.web.templates import render

router = APIRouter(tags=["web"])


# ── Auth ──────────────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    token = request.cookies.get("access_token")
    if token:
        # Logged-in users see the landing page with a dashboard link
        return render(request, "landing.html", {"logged_in": True, "current_user": None})
    return render(request, "landing.html", {"logged_in": False, "current_user": None})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return render(request, "auth/login.html", {"current_user": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = LoginRequest(email=email, password=password)
        tokens = await auth_service.login(db, data)
        await db.commit()
    except Exception:
        return render(
            request, "auth/login.html",
            {"current_user": None, "error": "Invalid email or password", "email": email},
            status_code=400,
        )

    response = RedirectResponse(url="/dashboard", status_code=302)
    set_auth_cookie(response, tokens.access_token)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return render(request, "auth/register.html", {"current_user": None})


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = RegisterRequest(name=name, email=email, password=password)
        await auth_service.register(db, data)
        await db.commit()
    except AppException as exc:
        return render(
            request, "auth/register.html",
            {"current_user": None, "error": exc.detail, "name": name, "email": email},
            status_code=400,
        )
    except Exception:
        return render(
            request, "auth/register.html",
            {"current_user": None, "error": "Registration failed. Check your input.",
             "name": name, "email": email},
            status_code=400,
        )

    return RedirectResponse(url="/login?registered=1", status_code=302)


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    # Best-effort: invalidate refresh token if present
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            await auth_service.logout(db, refresh_token)
            await db.commit()
        except Exception:
            pass

    response = RedirectResponse(url="/login", status_code=302)
    clear_auth_cookie(response)
    return response


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    groups = await group_service.list_user_groups(db, current_user.id)
    return render(request, "dashboard/index.html", {"current_user": current_user, "groups": groups})


# ── Groups ────────────────────────────────────────────────────────────────────


@router.get("/groups/new", response_class=HTMLResponse)
async def new_group_page(
    request: Request,
    current_user: UserPublic = Depends(get_current_web_user),
):
    return render(request, "groups/form.html", {"current_user": current_user})


@router.post("/groups", response_class=HTMLResponse)
async def create_group_submit(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = CreateGroupRequest(name=name, description=description or None)
        group = await group_service.create_group(db, current_user.id, data)
        await db.commit()
    except AppException as exc:
        return render(
            request, "groups/form.html",
            {"current_user": current_user, "error": exc.detail, "name": name, "description": description},
            status_code=400,
        )

    return RedirectResponse(url=f"/groups/{group.id}", status_code=302)


@router.get("/groups/{group_id}", response_class=HTMLResponse)
async def group_detail(
    request: Request,
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
    member_error: str | None = None,
):
    try:
        group = await group_service.get_group(db, group_id, current_user.id)
    except AppException:
        return RedirectResponse(url="/dashboard", status_code=302)

    expenses = await expense_service.list_group_expenses(db, group_id, current_user.id)
    settlements = await settlement_service.list_group_settlements(db, group_id, current_user.id)
    balance_data = await balance_service.get_group_balances(db, group_id, current_user.id)

    return render(request, "groups/detail.html", {
        "current_user": current_user,
        "group": group,
        "expenses": expenses,
        "settlements": settlements,
        "balances": balance_data.balances,
        "simplified_debts": balance_data.simplified_debts,
        "is_admin": group.current_user_role == "admin",
        "member_error": member_error,
    })


@router.post("/groups/{group_id}/members", response_class=HTMLResponse)
async def add_member_submit(
    request: Request,
    group_id: UUID,
    email: str = Form(...),
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = AddMemberRequest(email=email)
        await group_service.add_member(db, group_id, current_user.id, data)
        await db.commit()
    except AppException as exc:
        return await group_detail(request, group_id, current_user, db, member_error=exc.detail)

    return RedirectResponse(url=f"/groups/{group_id}", status_code=302)


# ── Expenses ──────────────────────────────────────────────────────────────────


@router.get("/groups/{group_id}/expenses/new", response_class=HTMLResponse)
async def new_expense_page(
    request: Request,
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        group = await group_service.get_group(db, group_id, current_user.id)
    except AppException:
        return RedirectResponse(url="/dashboard", status_code=302)

    return render(request, "expenses/form.html", {
        "current_user": current_user,
        "group": group,
        "members": group.members,
        "today": str(date.today()),
    })


@router.post("/groups/{group_id}/expenses", response_class=HTMLResponse)
async def create_expense_submit(
    request: Request,
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    description = form.get("description", "")
    amount_str = form.get("amount", "")
    payer_id_str = form.get("payer_id", "")
    expense_date_str = form.get("expense_date", str(date.today()))
    split_user_ids = form.getlist("split_user_ids")
    split_amounts = form.getlist("split_amounts")

    group = await group_service.get_group(db, group_id, current_user.id)

    def render_error(msg: str):
        return render(request, "expenses/form.html", {
            "current_user": current_user,
            "group": group,
            "members": group.members,
            "today": str(date.today()),
            "error": msg,
            "description": description,
            "amount": amount_str,
        }, status_code=400)

    try:
        amount = Decimal(amount_str)
        payer_id = UUID(payer_id_str)
        expense_date = date.fromisoformat(expense_date_str)

        splits = []
        for uid_str, amt_str in zip(split_user_ids, split_amounts):
            if amt_str and Decimal(amt_str) > 0:
                splits.append(ExpenseSplitRequest(user_id=UUID(uid_str), amount=Decimal(amt_str)))

        if not splits:
            return render_error("At least one split amount is required.")

        data = CreateExpenseRequest(
            description=description,
            amount=amount,
            payer_id=payer_id,
            expense_date=expense_date,
            splits=splits,
        )
        await expense_service.create_expense(db, group_id, current_user.id, data)
        await db.commit()
    except AppException as exc:
        return render_error(exc.detail)
    except (InvalidOperation, ValueError) as exc:
        return render_error(f"Invalid input: {exc}")

    return RedirectResponse(url=f"/groups/{group_id}", status_code=302)


@router.post("/expenses/{expense_id}/delete", response_class=HTMLResponse)
async def delete_expense_submit(
    expense_id: UUID,
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        expense = await expense_service.get_expense(db, expense_id, current_user.id)
        group_id = expense.group_id
        await expense_service.delete_expense(db, expense_id, current_user.id)
        await db.commit()
    except AppException:
        return RedirectResponse(url="/dashboard", status_code=302)

    return RedirectResponse(url=f"/groups/{group_id}", status_code=302)


@router.get("/expenses/{expense_id}/edit", response_class=HTMLResponse)
async def edit_expense_page(
    request: Request,
    expense_id: UUID,
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    """Show the expense form pre-filled with existing values."""
    try:
        expense = await expense_service.get_expense(db, expense_id, current_user.id)
    except AppException:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Only the creator can edit
    if str(expense.creator_id) != str(current_user.id):
        return RedirectResponse(url=f"/groups/{expense.group_id}", status_code=302)

    group = await group_service.get_group(db, expense.group_id, current_user.id)

    # Build a dict of existing split amounts keyed by user_id for template pre-fill
    existing_splits = {str(s.user_id): str(s.amount) for s in expense.splits}

    return render(request, "expenses/form.html", {
        "current_user": current_user,
        "group": group,
        "members": group.members,
        "today": str(date.today()),
        "editing": True,
        "expense_id": str(expense_id),
        "description": expense.description,
        "amount": str(expense.amount),
        "expense_date": str(expense.expense_date),
        "payer_id": str(expense.payer_id),
        "existing_splits": existing_splits,
    })


@router.post("/expenses/{expense_id}/edit", response_class=HTMLResponse)
async def update_expense_submit(
    request: Request,
    expense_id: UUID,
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    """Process the expense update form."""
    from app.schemas.expenses import UpdateExpenseRequest

    form = await request.form()
    description = form.get("description", "")
    amount_str = form.get("amount", "")
    payer_id_str = form.get("payer_id", "")
    expense_date_str = form.get("expense_date", str(date.today()))
    split_user_ids = form.getlist("split_user_ids")
    split_amounts = form.getlist("split_amounts")

    try:
        expense = await expense_service.get_expense(db, expense_id, current_user.id)
    except AppException:
        return RedirectResponse(url="/dashboard", status_code=302)

    group = await group_service.get_group(db, expense.group_id, current_user.id)
    existing_splits = {str(s.user_id): str(s.amount) for s in expense.splits}

    def render_error(msg: str):
        return render(request, "expenses/form.html", {
            "current_user": current_user,
            "group": group,
            "members": group.members,
            "today": str(date.today()),
            "editing": True,
            "expense_id": str(expense_id),
            "error": msg,
            "description": description,
            "amount": amount_str,
            "expense_date": expense_date_str,
            "payer_id": payer_id_str,
            "existing_splits": existing_splits,
        }, status_code=400)

    try:
        amount = Decimal(amount_str)
        payer_id = UUID(payer_id_str)
        expense_date = date.fromisoformat(expense_date_str)

        splits = []
        for uid_str, amt_str in zip(split_user_ids, split_amounts):
            if amt_str and Decimal(amt_str) > 0:
                splits.append(ExpenseSplitRequest(user_id=UUID(uid_str), amount=Decimal(amt_str)))

        if not splits:
            return render_error("At least one split amount is required.")

        data = UpdateExpenseRequest(
            description=description,
            amount=amount,
            payer_id=payer_id,
            expense_date=expense_date,
            splits=splits,
        )
        await expense_service.update_expense(db, expense_id, current_user.id, data)
        await db.commit()
    except AppException as exc:
        return render_error(exc.detail)
    except (InvalidOperation, ValueError) as exc:
        return render_error(f"Invalid input: {exc}")

    return RedirectResponse(url=f"/groups/{expense.group_id}", status_code=302)
# ── Settlements ───────────────────────────────────────────────────────────────


@router.get("/groups/{group_id}/settlements/new", response_class=HTMLResponse)
async def new_settlement_page(
    request: Request,
    group_id: UUID,
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        group = await group_service.get_group(db, group_id, current_user.id)
    except AppException:
        return RedirectResponse(url="/dashboard", status_code=302)

    return render(request, "settlements/form.html", {
        "current_user": current_user,
        "group": group,
        "members": group.members,
        "today": str(date.today()),
    })


@router.post("/groups/{group_id}/settlements", response_class=HTMLResponse)
async def create_settlement_submit(
    request: Request,
    group_id: UUID,
    payer_id: str = Form(...),
    payee_id: str = Form(...),
    amount: str = Form(...),
    settlement_date: str = Form(...),
    description: str = Form(default=""),
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    group = await group_service.get_group(db, group_id, current_user.id)

    def render_error(msg: str):
        return render(request, "settlements/form.html", {
            "current_user": current_user,
            "group": group,
            "members": group.members,
            "today": str(date.today()),
            "error": msg,
        }, status_code=400)

    try:
        data = CreateSettlementRequest(
            payer_id=UUID(payer_id),
            payee_id=UUID(payee_id),
            amount=Decimal(amount),
            settlement_date=date.fromisoformat(settlement_date),
            description=description or None,
        )
        await settlement_service.create_settlement(db, group_id, current_user.id, data)
        await db.commit()
    except AppException as exc:
        return render_error(exc.detail)
    except (InvalidOperation, ValueError) as exc:
        return render_error(f"Invalid input: {exc}")

    return RedirectResponse(url=f"/groups/{group_id}", status_code=302)


@router.post("/settlements/{settlement_id}/delete", response_class=HTMLResponse)
async def delete_settlement_submit(
    settlement_id: UUID,
    current_user: UserPublic = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        settlement = await settlement_service.get_settlement(db, settlement_id, current_user.id)
        group_id = settlement.group_id
        await settlement_service.delete_settlement(db, settlement_id, current_user.id)
        await db.commit()
    except AppException:
        return RedirectResponse(url="/dashboard", status_code=302)

    return RedirectResponse(url=f"/groups/{group_id}", status_code=302)
