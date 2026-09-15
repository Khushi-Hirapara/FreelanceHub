"""Admin-only platform management APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import require_roles
from app.models import (
    Contract,
    ContractStatus,
    Dispute,
    DisputeStatus,
    Payment,
    PaymentStatus,
    Project,
    ProjectStatus,
    User,
    UserRole,
)
from app.schemas import (
    AdminContractOut,
    AdminDashboardOut,
    AdminDisputeOut,
    AdminPage,
    AdminPaymentOut,
    AdminProjectOut,
    AdminUserOut,
    AdminUserStatusUpdate,
)

router = APIRouter(prefix="/admin", tags=["Admin"])

ACTIVE_CONTRACT_STATUSES = (
    ContractStatus.pending,
    ContractStatus.funded,
    ContractStatus.in_progress,
    ContractStatus.submitted,
    ContractStatus.approved,
    ContractStatus.disputed,
)


def _pages(total: int, limit: int) -> int:
    return (total + limit - 1) // limit if total else 0


@router.get("/dashboard", response_model=AdminDashboardOut)
def admin_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    total_users = int(db.scalar(select(func.count()).select_from(User)) or 0)
    clients = int(db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.client)) or 0)
    freelancers = int(
        db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.freelancer)) or 0
    )
    projects = int(db.scalar(select(func.count()).select_from(Project)) or 0)
    active_contracts = int(
        db.scalar(
            select(func.count()).select_from(Contract).where(Contract.status.in_(ACTIVE_CONTRACT_STATUSES))
        )
        or 0
    )
    completed_contracts = int(
        db.scalar(
            select(func.count()).select_from(Contract).where(Contract.status == ContractStatus.completed)
        )
        or 0
    )
    paid = db.execute(
        select(
            func.coalesce(func.sum(Payment.amount), 0),
            func.coalesce(func.sum(Payment.platform_fee), 0),
        ).where(Payment.status == PaymentStatus.paid)
    ).one()
    disputed_contracts = int(
        db.scalar(
            select(func.count()).select_from(Contract).where(Contract.status == ContractStatus.disputed)
        )
        or 0
    )
    pending_disputes = int(
        db.scalar(
            select(func.count())
            .select_from(Dispute)
            .where(Dispute.status.in_((DisputeStatus.open, DisputeStatus.under_review)))
        )
        or 0
    )
    return AdminDashboardOut(
        total_users=total_users,
        clients=clients,
        freelancers=freelancers,
        projects=projects,
        active_contracts=active_contracts,
        completed_contracts=completed_contracts,
        total_payment_volume=float(paid[0] or 0),
        platform_revenue=float(paid[1] or 0),
        pending_disputes=pending_disputes or disputed_contracts,
    )


@router.get("/users", response_model=AdminPage)
def admin_users(
    q: str | None = Query(default=None, max_length=120),
    role: UserRole | None = None,
    is_active: bool | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    filters = []
    query = (q or "").strip()
    if query:
        pattern = f"%{query}%"
        filters.append(or_(User.name.ilike(pattern), User.email.ilike(pattern), User.title.ilike(pattern)))
    if role is not None:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))

    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int(db.scalar(count_stmt) or 0)
    rows = db.scalars(
        stmt.order_by(User.created_at.desc(), User.id.desc()).offset((page - 1) * limit).limit(limit)
    ).all()
    return AdminPage(
        items=[AdminUserOut.model_validate(user) for user in rows],
        page=page,
        limit=limit,
        total=total,
        pages=_pages(total, limit),
    )


@router.patch("/users/{user_id}/status", response_model=AdminUserOut)
def admin_update_user_status(
    user_id: int,
    payload: AdminUserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id and not payload.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own account")
    if user.role == UserRole.admin and not payload.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin accounts cannot be deactivated here")
    user.is_active = payload.is_active
    db.add(user)
    db.commit()
    db.refresh(user)
    return AdminUserOut.model_validate(user)


@router.get("/projects", response_model=AdminPage)
def admin_projects(
    q: str | None = Query(default=None, max_length=120),
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    filters = []
    query = (q or "").strip()
    if query:
        pattern = f"%{query}%"
        filters.append(or_(Project.title.ilike(pattern), Project.category.ilike(pattern), Project.description.ilike(pattern)))
    if status_filter is not None:
        filters.append(Project.status == status_filter)

    stmt = select(Project).options(joinedload(Project.client), joinedload(Project.proposals))
    count_stmt = select(func.count()).select_from(Project)
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int(db.scalar(count_stmt) or 0)
    rows = db.scalars(
        stmt.order_by(Project.created_at.desc(), Project.id.desc()).offset((page - 1) * limit).limit(limit)
    ).unique().all()
    items = [
        AdminProjectOut(
            id=project.id,
            title=project.title,
            category=project.category,
            status=project.status,
            client_id=project.client_id,
            client_name=project.client.name if project.client else None,
            budget_min=project.budget_min,
            budget_max=project.budget_max,
            proposal_count=len(project.proposals or []),
            created_at=project.created_at,
        )
        for project in rows
    ]
    return AdminPage(items=items, page=page, limit=limit, total=total, pages=_pages(total, limit))


@router.get("/contracts", response_model=AdminPage)
def admin_contracts(
    q: str | None = Query(default=None, max_length=120),
    status_filter: ContractStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    filters = []
    if status_filter is not None:
        filters.append(Contract.status == status_filter)
    query = (q or "").strip()

    stmt = select(Contract).options(
        joinedload(Contract.project),
        joinedload(Contract.client),
        joinedload(Contract.freelancer),
    )
    count_stmt = select(func.count()).select_from(Contract)
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)
    if query:
        pattern = f"%{query}%"
        stmt = stmt.join(Contract.project).where(Project.title.ilike(pattern))
        count_stmt = count_stmt.join(Contract.project).where(Project.title.ilike(pattern))

    total = int(db.scalar(count_stmt) or 0)
    rows = db.scalars(
        stmt.order_by(Contract.created_at.desc(), Contract.id.desc()).offset((page - 1) * limit).limit(limit)
    ).unique().all()
    items = [
        AdminContractOut(
            id=contract.id,
            project_id=contract.project_id,
            project_title=contract.project.title if contract.project else None,
            client_id=contract.client_id,
            client_name=contract.client.name if contract.client else None,
            freelancer_id=contract.freelancer_id,
            freelancer_name=contract.freelancer.name if contract.freelancer else None,
            agreed_amount=float(contract.agreed_amount),
            platform_fee=float(contract.platform_fee),
            status=contract.status,
            created_at=contract.created_at,
        )
        for contract in rows
    ]
    return AdminPage(items=items, page=page, limit=limit, total=total, pages=_pages(total, limit))


@router.get("/payments", response_model=AdminPage)
def admin_payments(
    q: str | None = Query(default=None, max_length=120),
    status_filter: PaymentStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    filters = []
    if status_filter is not None:
        filters.append(Payment.status == status_filter)
    query = (q or "").strip()
    if query:
        pattern = f"%{query}%"
        filters.append(
            or_(
                Payment.transaction_id.ilike(pattern),
                Payment.currency.ilike(pattern),
            )
        )

    stmt = select(Payment).options(joinedload(Payment.contract).joinedload(Contract.project))
    count_stmt = select(func.count()).select_from(Payment)
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int(db.scalar(count_stmt) or 0)
    rows = db.scalars(
        stmt.order_by(Payment.created_at.desc(), Payment.id.desc()).offset((page - 1) * limit).limit(limit)
    ).unique().all()
    items = [
        AdminPaymentOut(
            id=payment.id,
            contract_id=payment.contract_id,
            milestone_id=payment.milestone_id,
            client_id=payment.client_id,
            freelancer_id=payment.freelancer_id,
            amount=float(payment.amount),
            platform_fee=float(payment.platform_fee),
            freelancer_amount=float(payment.freelancer_amount),
            status=payment.status,
            transaction_id=payment.transaction_id,
            paid_at=payment.paid_at,
            created_at=payment.created_at,
            project_title=payment.contract.project.title
            if payment.contract and payment.contract.project
            else None,
        )
        for payment in rows
    ]
    return AdminPage(items=items, page=page, limit=limit, total=total, pages=_pages(total, limit))


@router.get("/disputes", response_model=AdminPage)
def admin_disputes(
    q: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    filters = [Dispute.status.in_((DisputeStatus.open, DisputeStatus.under_review))]
    query = (q or "").strip()
    stmt = (
        select(Dispute)
        .options(
            joinedload(Dispute.contract).joinedload(Contract.project),
            joinedload(Dispute.opener),
        )
        .where(*filters)
        .order_by(Dispute.updated_at.desc(), Dispute.id.desc())
    )
    rows = db.scalars(stmt).unique().all()
    items: list[AdminDisputeOut] = []
    for dispute in rows:
        contract = dispute.contract
        project_title = contract.project.title if contract and contract.project else f"Contract #{dispute.contract_id}"
        haystack = f"{project_title} {dispute.reason} {dispute.description} {dispute.contract_id}".lower()
        if query and query.lower() not in haystack:
            continue
        items.append(
            AdminDisputeOut(
                kind="dispute",
                id=dispute.id,
                status=dispute.status.value,
                title=project_title,
                reason=dispute.reason,
                description=dispute.description,
                contract_id=dispute.contract_id,
                project_id=contract.project_id if contract else None,
                opened_by=dispute.opened_by,
                client_id=contract.client_id if contract else 0,
                freelancer_id=contract.freelancer_id if contract else 0,
                resolution=dispute.resolution.value if dispute.resolution else None,
                resolution_notes=dispute.resolution_notes,
                partial_amount=float(dispute.partial_amount) if dispute.partial_amount is not None else None,
                updated_at=dispute.updated_at,
                created_at=dispute.created_at,
            )
        )

    total = len(items)
    start = (page - 1) * limit
    slice_items = items[start : start + limit]
    return AdminPage(items=slice_items, page=page, limit=limit, total=total, pages=_pages(total, limit))
