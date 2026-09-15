from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.contract_flow import accept_proposal_and_create_contract
from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import Project, ProjectStatus, Proposal, ProposalStatus, User, UserRole
from app.routers.users import public_user
from app.schemas import ProposalCreate, ProposalOut, ProposalStatusUpdate, ProjectOut

router = APIRouter(tags=["Proposals"])


def serialize_proposal(proposal: Proposal, include_project: bool = False) -> ProposalOut:
    data = ProposalOut(
        id=proposal.id,
        project_id=proposal.project_id,
        freelancer_id=proposal.freelancer_id,
        bid_amount=proposal.bid_amount,
        estimated_duration=proposal.estimated_duration,
        cover_letter=proposal.cover_letter,
        milestones=proposal.milestones or [],
        status=proposal.status,
        created_at=proposal.created_at,
        contract_id=proposal.contract.id if proposal.contract else None,
        freelancer=public_user(proposal.freelancer) if proposal.freelancer else None,
        project=None,
    )
    if include_project and proposal.project:
        data.project = ProjectOut(
            id=proposal.project.id,
            client_id=proposal.project.client_id,
            title=proposal.project.title,
            category=proposal.project.category,
            description=proposal.project.description,
            skills=proposal.project.skills or [],
            budget_min=proposal.project.budget_min,
            budget_max=proposal.project.budget_max,
            deadline=proposal.project.deadline,
            experience_level=proposal.project.experience_level,
            status=proposal.project.status,
            proposal_count=0,
            created_at=proposal.project.created_at,
            client=None,
        )
    return data


@router.post("/proposals", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def create_proposal(
    payload: ProposalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.freelancer)),
):
    project = db.get(Project, payload.project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.status != ProjectStatus.open:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project is not open for bids")
    if project.client_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot bid on your own project")

    existing = db.scalar(
        select(Proposal).where(
            Proposal.project_id == payload.project_id,
            Proposal.freelancer_id == current_user.id,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You already submitted a proposal")

    proposal = Proposal(
        project_id=payload.project_id,
        freelancer_id=current_user.id,
        bid_amount=payload.bid_amount,
        estimated_duration=payload.estimated_duration,
        cover_letter=payload.cover_letter.strip(),
        milestones=[m.model_dump() for m in payload.milestones],
        status=ProposalStatus.pending,
    )
    db.add(proposal)
    db.flush()
    from app.notify import notify

    notify(
        db,
        project.client_id,
        kind="new_proposal",
        title="New proposal",
        message=f"{current_user.name} submitted a proposal for “{project.title}”.",
        related_type="project",
        related_id=project.id,
        actor_id=current_user.id,
    )
    db.commit()
    db.refresh(proposal)

    proposal = db.scalars(
        select(Proposal)
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project), joinedload(Proposal.contract))
        .where(Proposal.id == proposal.id)
    ).unique().one()
    return serialize_proposal(proposal, include_project=True)


@router.get("/proposals/mine", response_model=list[ProposalOut])
def my_proposals(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.freelancer)),
):
    proposals = db.scalars(
        select(Proposal)
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project), joinedload(Proposal.contract))
        .where(Proposal.freelancer_id == current_user.id)
        .order_by(Proposal.created_at.desc())
    ).unique().all()
    return [serialize_proposal(p, include_project=True) for p in proposals]


@router.get("/projects/{project_id}/proposals", response_model=list[ProposalOut])
def project_proposals(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.client_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your project")

    proposals = db.scalars(
        select(Proposal)
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project), joinedload(Proposal.contract))
        .where(Proposal.project_id == project_id)
        .order_by(Proposal.created_at.desc())
    ).unique().all()
    return [serialize_proposal(p) for p in proposals]


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
def get_proposal(
    proposal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = db.scalars(
        select(Proposal)
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project), joinedload(Proposal.contract))
        .where(Proposal.id == proposal_id)
    ).unique().first()
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

    is_owner = proposal.freelancer_id == current_user.id
    is_client = proposal.project and proposal.project.client_id == current_user.id
    if not (is_owner or is_client or current_user.role == UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return serialize_proposal(proposal, include_project=True)


@router.patch("/proposals/{proposal_id}", response_model=ProposalOut)
def update_proposal_status(
    proposal_id: int,
    payload: ProposalStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = db.scalars(
        select(Proposal)
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project), joinedload(Proposal.contract))
        .where(Proposal.id == proposal_id)
    ).unique().first()
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

    project = proposal.project
    if payload.status == ProposalStatus.withdrawn:
        if proposal.freelancer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the freelancer can withdraw")
    elif payload.status in (ProposalStatus.accepted, ProposalStatus.rejected):
        if project.client_id != current_user.id and current_user.role != UserRole.admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the client can accept/reject")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported status change")

    if payload.status == ProposalStatus.accepted:
        try:
            accept_proposal_and_create_contract(db, proposal, current_user)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A contract already exists for this project or proposal",
            ) from None
        proposal = db.scalars(
            select(Proposal)
            .options(
                joinedload(Proposal.freelancer),
                joinedload(Proposal.project),
                joinedload(Proposal.contract),
            )
            .where(Proposal.id == proposal_id)
        ).unique().one()
        return serialize_proposal(proposal, include_project=True)

    if payload.status == ProposalStatus.rejected and proposal.status != ProposalStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a pending proposal can be rejected")
    if payload.status == ProposalStatus.withdrawn and proposal.status != ProposalStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a pending proposal can be withdrawn")

    proposal.status = payload.status
    db.add(proposal)
    if payload.status == ProposalStatus.rejected:
        from app.notify import notify

        title = project.title if project else "a project"
        notify(
            db,
            proposal.freelancer_id,
            kind="proposal_rejected",
            title="Proposal rejected",
            message=f"Your proposal for “{title}” was rejected.",
            related_type="project",
            related_id=proposal.project_id,
            actor_id=current_user.id,
        )
    db.commit()
    db.refresh(proposal)
    return serialize_proposal(proposal, include_project=True)
