from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.contract_flow import accept_proposal_and_create_contract, apply_contract_status, user_can_access_contract
from app.database import get_db
from app.deps import get_current_user
from app.models import Contract, Project, Proposal, User, UserRole
from app.schemas import ContractCreate, ContractOut, ContractPartyOut, ContractProjectOut, ContractStatusUpdate

router = APIRouter(tags=["Contracts"])


def serialize_contract(contract: Contract) -> ContractOut:
    return ContractOut(
        id=contract.id,
        project_id=contract.project_id,
        proposal_id=contract.proposal_id,
        client_id=contract.client_id,
        freelancer_id=contract.freelancer_id,
        agreed_amount=float(contract.agreed_amount),
        platform_fee=float(contract.platform_fee),
        freelancer_amount=float(contract.freelancer_amount),
        currency=contract.currency,
        status=contract.status,
        start_date=contract.start_date,
        end_date=contract.end_date,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        project=ContractProjectOut.model_validate(contract.project) if contract.project else None,
        client=ContractPartyOut.model_validate(contract.client) if contract.client else None,
        freelancer=ContractPartyOut.model_validate(contract.freelancer) if contract.freelancer else None,
    )


def load_contract(db: Session, contract_id: int) -> Contract | None:
    return db.scalars(
        select(Contract)
        .options(
            joinedload(Contract.project),
            joinedload(Contract.client),
            joinedload(Contract.freelancer),
        )
        .where(Contract.id == contract_id)
    ).unique().first()


def require_contract_access(contract: Contract, user: User) -> None:
    if not user_can_access_contract(user, contract):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("/contracts", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: ContractCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.client, UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a client can create a contract")

    proposal = db.scalars(
        select(Proposal).options(joinedload(Proposal.project)).where(Proposal.id == payload.proposal_id)
    ).unique().first()
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

    contract = accept_proposal_and_create_contract(db, proposal, current_user)
    db.commit()
    loaded = load_contract(db, contract.id)
    return serialize_contract(loaded)


@router.get("/contracts/mine", response_model=list[ContractOut])
def my_contracts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Contract).options(
        joinedload(Contract.project),
        joinedload(Contract.client),
        joinedload(Contract.freelancer),
    )
    if current_user.role != UserRole.admin:
        stmt = stmt.where(
            or_(Contract.client_id == current_user.id, Contract.freelancer_id == current_user.id)
        )
    stmt = stmt.order_by(Contract.created_at.desc())
    contracts = db.scalars(stmt).unique().all()
    return [serialize_contract(item) for item in contracts]


@router.get("/projects/{project_id}/contract", response_model=ContractOut)
def contract_for_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    contract = db.scalars(
        select(Contract)
        .options(
            joinedload(Contract.project),
            joinedload(Contract.client),
            joinedload(Contract.freelancer),
        )
        .where(Contract.project_id == project_id)
    ).unique().first()
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No contract for this project")
    require_contract_access(contract, current_user)
    return serialize_contract(contract)


@router.get("/contracts/{contract_id}", response_model=ContractOut)
def get_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = load_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    require_contract_access(contract, current_user)
    return serialize_contract(contract)


@router.patch("/contracts/{contract_id}", response_model=ContractOut)
def update_contract_status(
    contract_id: int,
    payload: ContractStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = load_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    apply_contract_status(db, contract, current_user, payload.status)
    db.add(contract)
    db.commit()
    loaded = load_contract(db, contract.id)
    return serialize_contract(loaded)
