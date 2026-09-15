"""Contract dispute APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.contract_flow import user_can_access_contract
from app.database import get_db
from app.deps import get_current_user, require_roles
from app.dispute_flow import (
    load_dispute,
    open_dispute,
    resolve_dispute,
    update_dispute,
    user_can_access_dispute,
)
from app.models import Contract, Dispute, User, UserRole
from app.schemas import DisputeCreate, DisputeOut, DisputeResolve, DisputeUpdate

router = APIRouter(tags=["Disputes"])


def serialize_dispute(dispute: Dispute) -> DisputeOut:
    contract = dispute.contract
    project_title = None
    contract_status = None
    if contract is not None:
        contract_status = contract.status
        if contract.project is not None:
            project_title = contract.project.title
    return DisputeOut(
        id=dispute.id,
        contract_id=dispute.contract_id,
        opened_by=dispute.opened_by,
        reason=dispute.reason,
        description=dispute.description,
        status=dispute.status,
        resolution=dispute.resolution,
        resolution_notes=dispute.resolution_notes,
        partial_amount=float(dispute.partial_amount) if dispute.partial_amount is not None else None,
        resolved_by=dispute.resolved_by,
        resolved_at=dispute.resolved_at,
        created_at=dispute.created_at,
        updated_at=dispute.updated_at,
        project_title=project_title,
        opener_name=dispute.opener.name if dispute.opener else None,
        resolver_name=dispute.resolver.name if dispute.resolver else None,
        contract_status=contract_status,
    )


@router.post(
    "/contracts/{contract_id}/disputes",
    response_model=DisputeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_dispute(
    contract_id: int,
    payload: DisputeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.scalars(
        select(Contract).options(joinedload(Contract.project)).where(Contract.id == contract_id)
    ).unique().first()
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    try:
        dispute = open_dispute(db, contract, current_user, payload.reason, payload.description)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active dispute already exists for this contract",
        ) from None
    loaded = load_dispute(db, dispute.id)
    return serialize_dispute(loaded)


@router.get("/disputes/mine", response_model=list[DisputeOut])
def my_disputes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.admin:
        rows = db.scalars(
            select(Dispute)
            .options(
                joinedload(Dispute.contract).joinedload(Contract.project),
                joinedload(Dispute.opener),
                joinedload(Dispute.resolver),
            )
            .order_by(Dispute.updated_at.desc(), Dispute.id.desc())
        ).unique().all()
    else:
        rows = db.scalars(
            select(Dispute)
            .join(Contract, Dispute.contract_id == Contract.id)
            .options(
                joinedload(Dispute.contract).joinedload(Contract.project),
                joinedload(Dispute.opener),
                joinedload(Dispute.resolver),
            )
            .where(
                or_(
                    Dispute.opened_by == current_user.id,
                    Contract.client_id == current_user.id,
                    Contract.freelancer_id == current_user.id,
                )
            )
            .order_by(Dispute.updated_at.desc(), Dispute.id.desc())
        ).unique().all()
    return [serialize_dispute(item) for item in rows]


@router.get("/disputes/{dispute_id}", response_model=DisputeOut)
def get_dispute(
    dispute_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dispute = load_dispute(db, dispute_id)
    if not dispute:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found")
    if not user_can_access_dispute(current_user, dispute):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return serialize_dispute(dispute)


@router.patch("/disputes/{dispute_id}", response_model=DisputeOut)
def patch_dispute(
    dispute_id: int,
    payload: DisputeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dispute = load_dispute(db, dispute_id)
    if not dispute:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided")
    update_dispute(db, dispute, current_user, changes)
    db.commit()
    loaded = load_dispute(db, dispute_id)
    return serialize_dispute(loaded)


@router.get("/contracts/{contract_id}/disputes", response_model=list[DisputeOut])
def disputes_for_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    if current_user.role != UserRole.admin and not user_can_access_contract(current_user, contract):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    rows = db.scalars(
        select(Dispute)
        .options(
            joinedload(Dispute.contract).joinedload(Contract.project),
            joinedload(Dispute.opener),
            joinedload(Dispute.resolver),
        )
        .where(Dispute.contract_id == contract_id)
        .order_by(Dispute.created_at.desc(), Dispute.id.desc())
    ).unique().all()
    return [serialize_dispute(item) for item in rows]


@router.patch("/admin/disputes/{dispute_id}/resolve", response_model=DisputeOut)
def admin_resolve_dispute(
    dispute_id: int,
    payload: DisputeResolve,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    dispute = load_dispute(db, dispute_id)
    if not dispute:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found")
    resolve_dispute(
        db,
        dispute,
        current_user,
        outcome=payload.outcome,
        resolution=payload.resolution,
        partial_amount=payload.partial_amount,
        notes=payload.notes,
    )
    db.commit()
    loaded = load_dispute(db, dispute_id)
    return serialize_dispute(loaded)
