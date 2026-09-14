"""Accept a proposal and create the matching contract. Shared by proposal + contract routes."""

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import split_agreed_amount
from app.models import (
    Contract,
    ContractStatus,
    Project,
    ProjectStatus,
    Proposal,
    ProposalStatus,
    User,
    UserRole,
    utcnow,
)

# Who may move a contract from -> to. Party checks happen separately.
ALLOWED_TRANSITIONS: dict[ContractStatus, dict[ContractStatus, set[UserRole]]] = {
    ContractStatus.pending: {
        # Recorded only. No charge is taken. UI does not expose a pay button.
        ContractStatus.funded: {UserRole.admin},
        ContractStatus.cancelled: {UserRole.client, UserRole.admin},
    },
    ContractStatus.funded: {
        ContractStatus.in_progress: {UserRole.freelancer, UserRole.admin},
        ContractStatus.cancelled: {UserRole.client, UserRole.admin},
    },
    ContractStatus.in_progress: {
        ContractStatus.submitted: {UserRole.freelancer, UserRole.admin},
        ContractStatus.cancelled: {UserRole.client, UserRole.admin},
        ContractStatus.disputed: {UserRole.client, UserRole.freelancer, UserRole.admin},
    },
    ContractStatus.submitted: {
        ContractStatus.approved: {UserRole.client, UserRole.admin},
        ContractStatus.disputed: {UserRole.client, UserRole.freelancer, UserRole.admin},
    },
    ContractStatus.approved: {
        ContractStatus.completed: {UserRole.client, UserRole.admin},
    },
    ContractStatus.disputed: {
        ContractStatus.in_progress: {UserRole.admin},
        ContractStatus.cancelled: {UserRole.admin},
    },
    ContractStatus.completed: {},
    ContractStatus.cancelled: {},
}


def user_can_access_contract(user: User, contract: Contract) -> bool:
    if user.role == UserRole.admin:
        return True
    return user.id in (contract.client_id, contract.freelancer_id)


def accept_proposal_and_create_contract(db: Session, proposal: Proposal, actor: User) -> Contract:
    project = proposal.project
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if actor.role != UserRole.admin and project.client_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the client can accept a proposal")

    if proposal.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proposal does not belong to this project")

    if proposal.status != ProposalStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a pending proposal can be accepted")

    if project.status != ProjectStatus.open:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project is not open for acceptance")

    existing = db.scalar(select(Contract).where(Contract.project_id == project.id))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A contract already exists for this project")

    existing_proposal = db.scalar(select(Contract).where(Contract.proposal_id == proposal.id))
    if existing_proposal:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A contract already exists for this proposal")

    agreed, fee, freelancer_amount = split_agreed_amount(proposal.bid_amount)
    contract = Contract(
        project_id=project.id,
        proposal_id=proposal.id,
        client_id=project.client_id,
        freelancer_id=proposal.freelancer_id,
        agreed_amount=agreed,
        platform_fee=fee,
        freelancer_amount=freelancer_amount,
        currency="USD",
        status=ContractStatus.pending,
    )
    proposal.status = ProposalStatus.accepted
    project.status = ProjectStatus.in_progress

    others = db.scalars(
        select(Proposal).where(
            Proposal.project_id == project.id,
            Proposal.id != proposal.id,
            Proposal.status == ProposalStatus.pending,
        )
    ).all()
    for other in others:
        other.status = ProposalStatus.rejected
        db.add(other)

    db.add(contract)
    db.add(proposal)
    db.add(project)
    db.flush()
    return contract


def apply_contract_status(contract: Contract, actor: User, new_status: ContractStatus) -> None:
    if not user_can_access_contract(actor, contract):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if new_status == contract.status:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contract is already in that status")

    allowed = ALLOWED_TRANSITIONS.get(contract.status, {}).get(new_status)
    if not allowed or actor.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change contract from {contract.status.value} to {new_status.value}",
        )

    if actor.role != UserRole.admin:
        if actor.role == UserRole.client and actor.id != contract.client_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your contract")
        if actor.role == UserRole.freelancer and actor.id != contract.freelancer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your contract")

    contract.status = new_status
    today = date.today()
    if new_status == ContractStatus.in_progress and contract.start_date is None:
        contract.start_date = today
    if new_status == ContractStatus.completed:
        contract.end_date = today
    contract.updated_at = utcnow()
