from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import Project, ProjectStatus, Proposal, ProposalStatus, User, UserRole
from app.schemas import ProposalCreate, ProposalOut, ProposalStatusUpdate, ProjectOut, UserOut

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
        freelancer=UserOut.model_validate(proposal.freelancer) if proposal.freelancer else None,
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
    db.commit()
    db.refresh(proposal)

    proposal = db.scalars(
        select(Proposal)
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project))
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
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project))
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
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project))
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
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project))
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
        .options(joinedload(Proposal.freelancer), joinedload(Proposal.project))
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

    proposal.status = payload.status

    if payload.status == ProposalStatus.accepted:
        project.status = ProjectStatus.in_progress
        # Reject other pending proposals on the same project
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
        db.add(project)

    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return serialize_proposal(proposal, include_project=True)
