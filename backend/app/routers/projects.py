from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import Project, ProjectStatus, User, UserRole
from app.schemas import ProjectCreate, ProjectOut, ProjectUpdate, UserOut

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
        client=UserOut.model_validate(project.client) if project.client else None,
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

    for key, value in payload.model_dump(exclude_unset=True).items():
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
