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
        # Funded only by the mock payment confirmation, never by a status patch.
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
    from app.milestone_flow import seed_from_proposal

    seed_from_proposal(db, contract, proposal)
    title = project.title
    from app.notify import notify

    notify(
        db,
        proposal.freelancer_id,
        kind="proposal_accepted",
        title="Proposal accepted",
        message=f"Your proposal for “{title}” was accepted.",
        related_type="contract",
        related_id=contract.id,
        actor_id=actor.id,
    )
    notify(
        db,
        proposal.freelancer_id,
        kind="contract_created",
        title="Contract created",
        message=f"A contract is ready for “{title}”.",
        related_type="contract",
        related_id=contract.id,
        actor_id=actor.id,
    )
    for other in others:
        notify(
            db,
            other.freelancer_id,
            kind="proposal_rejected",
            title="Proposal not selected",
            message=f"Another proposal was accepted for “{title}”.",
            related_type="project",
            related_id=project.id,
            actor_id=actor.id,
        )
    return contract


def apply_contract_status(db: Session, contract: Contract, actor: User, new_status: ContractStatus) -> None:
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

    previous = contract.status
    if new_status in (ContractStatus.approved, ContractStatus.completed):
        complete_contract(contract)
        _notify_completed(db, contract, actor)
        return

    contract.status = new_status
    if new_status == ContractStatus.in_progress and contract.start_date is None:
        contract.start_date = date.today()
    contract.updated_at = utcnow()
    if new_status == ContractStatus.disputed:
        _notify_dispute(db, contract, actor, opened=True)
    elif previous == ContractStatus.disputed:
        _notify_dispute(db, contract, actor, opened=False)


def complete_contract(contract: Contract) -> None:
    """Approve-and-complete. Reviews stay closed until this runs."""
    if contract.status == ContractStatus.completed:
        return
    contract.status = ContractStatus.completed
    contract.end_date = date.today()
    contract.updated_at = utcnow()
    if contract.project is not None and contract.project.status != ProjectStatus.cancelled:
        contract.project.status = ProjectStatus.completed
        contract.project.updated_at = utcnow()
    freelancer = contract.freelancer
    if freelancer is not None:
        freelancer.projects_done = int(freelancer.projects_done or 0) + 1


def _contract_label(contract: Contract) -> str:
    project = getattr(contract, "project", None)
    return project.title if project is not None else "your contract"


def _notify_completed(db: Session, contract: Contract, actor: User) -> None:
    from app.notify import notify_many

    notify_many(
        db,
        [contract.client_id, contract.freelancer_id],
        actor_id=None,
        kind="contract_completed",
        title="Contract completed",
        message=f"“{_contract_label(contract)}” is complete. You can leave a review.",
        related_type="contract",
        related_id=contract.id,
    )
    _ = actor


def _notify_dispute(db: Session, contract: Contract, actor: User, *, opened: bool) -> None:
    from app.notify import notify_many

    title = _contract_label(contract)
    if opened:
        notify_many(
            db,
            [contract.client_id, contract.freelancer_id],
            actor_id=actor.id,
            kind="dispute_opened",
            title="Dispute opened",
            message=f"A dispute was opened on “{title}”.",
            related_type="contract",
            related_id=contract.id,
        )
        return
    notify_many(
        db,
        [contract.client_id, contract.freelancer_id],
        actor_id=None,
        kind="dispute_resolved",
        title="Dispute resolved",
        message=f"The dispute on “{title}” was resolved.",
        related_type="contract",
        related_id=contract.id,
    )
