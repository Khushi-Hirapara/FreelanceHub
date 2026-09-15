from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.freelancer_matching import recommend_freelancers
from app.models import Project, ProjectStatus, User, UserRole
from app.schemas import ProjectCreate, ProjectOut, ProjectUpdate, RecommendedFreelancerOut
from app.routers.users import public_user

router = APIRouter(prefix="/projects", tags=["Projects"])


def serialize_project(project: Project) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        client_id=project.client_id,
        title=project.title,
        category=project.category,
        description=project.description,
        skills=project.skills or [],
        budget_min=project.budget_min,
        budget_max=project.budget_max,
        deadline=project.deadline,
        experience_level=project.experience_level,
        status=project.status,
        proposal_count=len(project.proposals) if project.proposals is not None else 0,
        created_at=project.created_at,
        client=public_user(project.client) if project.client else None,
    )


@router.get("", response_model=list[ProjectOut])
def list_projects(
    q: str | None = None,
    category: str | None = None,
    max_budget: float | None = None,
    status_filter: ProjectStatus | None = Query(default=ProjectStatus.open, alias="status"),
    db: Session = Depends(get_db),
):
    stmt = select(Project).options(joinedload(Project.client), joinedload(Project.proposals))

    if status_filter is not None:
        stmt = stmt.where(Project.status == status_filter)
    if category and category.lower() != "all":
        stmt = stmt.where(func.lower(Project.category) == category.lower())
    if max_budget is not None:
        stmt = stmt.where(Project.budget_min <= max_budget)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Project.title).like(like),
                func.lower(Project.description).like(like),
            )
        )

    stmt = stmt.order_by(Project.created_at.desc())
    projects = db.scalars(stmt).unique().all()
    return [serialize_project(p) for p in projects]


@router.get("/mine", response_model=list[ProjectOut])
def my_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.client, UserRole.admin)),
):
    stmt = (
        select(Project)
        .options(joinedload(Project.client), joinedload(Project.proposals))
        .where(Project.client_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    projects = db.scalars(stmt).unique().all()
    return [serialize_project(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.client, UserRole.admin)),
):
    project = Project(
        client_id=current_user.id,
        title=payload.title.strip(),
        category=payload.category,
        description=payload.description.strip(),
        skills=payload.skills or [],
        budget_min=payload.budget_min,
        budget_max=payload.budget_max,
        deadline=payload.deadline,
        experience_level=payload.experience_level,
        status=ProjectStatus.open,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    project = db.scalars(
        select(Project)
        .options(joinedload(Project.client), joinedload(Project.proposals))
        .where(Project.id == project.id)
    ).unique().one()
    return serialize_project(project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.scalars(
        select(Project)
        .options(joinedload(Project.client), joinedload(Project.proposals))
        .where(Project.id == project_id)
    ).unique().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return serialize_project(project)


@router.get("/{project_id}/recommended-freelancers", response_model=list[RecommendedFreelancerOut])
def recommended_freelancers(
    project_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.client, UserRole.admin)),
):
    """Rank freelancers for a project. Deterministic scoring; embeddings can plug in later."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if current_user.role != UserRole.admin and project.client_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your project")
    return recommend_freelancers(db, project, limit=limit)


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.client_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your project")

    locked = {ProjectStatus.completed, ProjectStatus.cancelled}
    if project.status in locked and current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Completed or cancelled projects cannot be edited",
        )

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided")
    if "status" in changes and current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only an admin can change project status",
        )

    for key in ("title", "category", "description", "experience_level"):
        if isinstance(changes.get(key), str):
            changes[key] = changes[key].strip()
            if key != "experience_level" and not changes[key]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} cannot be blank")

    next_min = changes.get("budget_min", project.budget_min)
    next_max = changes.get("budget_max", project.budget_max)
    if next_min is None or next_max is None or next_min <= 0 or next_max <= 0 or next_max < next_min:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Budget maximum must be greater than or equal to the minimum",
        )

    for key, value in changes.items():
        setattr(project, key, value)

    db.add(project)
    db.commit()

    project = db.scalars(
        select(Project)
        .options(joinedload(Project.client), joinedload(Project.proposals))
        .where(Project.id == project_id)
    ).unique().one()
    return serialize_project(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.client_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your project")
    db.delete(project)
    db.commit()
