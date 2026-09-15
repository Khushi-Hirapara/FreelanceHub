"""Attachment authorization and persistence. Storage keys stay server-side."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from fastapi import HTTPException, status

from app.models import Attachment, Contract, Conversation, Milestone, Project, Proposal, User, UserRole, utcnow
from app.storage import get_storage, new_storage_key


def user_can_access_project(db: Session, user: User, project: Project) -> bool:
    if user.role == UserRole.admin or project.client_id == user.id:
        return True
    has_proposal = db.scalar(
        select(Proposal.id).where(Proposal.project_id == project.id, Proposal.freelancer_id == user.id)
    )
    if has_proposal:
        return True
    has_contract = db.scalar(
        select(Contract.id).where(Contract.project_id == project.id, Contract.freelancer_id == user.id)
    )
    return bool(has_contract)


def user_can_access_contract(user: User, contract: Contract) -> bool:
    if user.role == UserRole.admin:
        return True
    return user.id in (contract.client_id, contract.freelancer_id)


def user_can_access_conversation(user: User, conversation: Conversation) -> bool:
    if user.role == UserRole.admin:
        return True
    return user.id in (conversation.participant_one_id, conversation.participant_two_id)


def user_can_access_milestone(db: Session, user: User, milestone: Milestone) -> bool:
    contract = milestone.contract or db.get(Contract, milestone.contract_id)
    if not contract:
        return False
    return user_can_access_contract(user, contract)


def require_parent_access(
    db: Session,
    user: User,
    *,
    project_id: int | None = None,
    contract_id: int | None = None,
    conversation_id: int | None = None,
    milestone_id: int | None = None,
) -> dict:
    parents = {
        "project_id": project_id,
        "contract_id": contract_id,
        "conversation_id": conversation_id,
        "milestone_id": milestone_id,
    }
    if not any(parents.values()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attach the file to a project, contract, conversation, or milestone",
        )

    if project_id is not None:
        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if not user_can_access_project(db, user, project):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if contract_id is not None:
        contract = db.get(Contract, contract_id)
        if not contract:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
        if not user_can_access_contract(user, contract):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if conversation_id is not None:
        conversation = db.get(Conversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        if not user_can_access_conversation(user, conversation):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if milestone_id is not None:
        milestone = db.get(Milestone, milestone_id)
        if not milestone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
        if not user_can_access_milestone(db, user, milestone):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if contract_id is None:
            parents["contract_id"] = milestone.contract_id
    return parents


def user_can_access_attachment(db: Session, user: User, attachment: Attachment) -> bool:
    if user.role == UserRole.admin or attachment.uploader_id == user.id:
        return True
    if attachment.project_id:
        project = db.get(Project, attachment.project_id)
        if project and user_can_access_project(db, user, project):
            return True
    if attachment.contract_id:
        contract = db.get(Contract, attachment.contract_id)
        if contract and user_can_access_contract(user, contract):
            return True
    if attachment.conversation_id:
        conversation = db.get(Conversation, attachment.conversation_id)
        if conversation and user_can_access_conversation(user, conversation):
            return True
    if attachment.milestone_id:
        milestone = db.get(Milestone, attachment.milestone_id)
        if milestone and user_can_access_milestone(db, user, milestone):
            return True
    return False


def user_can_delete_attachment(db: Session, user: User, attachment: Attachment) -> bool:
    if user.role == UserRole.admin or attachment.uploader_id == user.id:
        return True
    if attachment.project_id:
        project = db.get(Project, attachment.project_id)
        if project and project.client_id == user.id:
            return True
    if attachment.contract_id:
        contract = db.get(Contract, attachment.contract_id)
        if contract and contract.client_id == user.id:
            return True
    return False


def create_attachment(
    db: Session,
    user: User,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    project_id: int | None = None,
    contract_id: int | None = None,
    conversation_id: int | None = None,
    milestone_id: int | None = None,
) -> Attachment:
    parents = require_parent_access(
        db,
        user,
        project_id=project_id,
        contract_id=contract_id,
        conversation_id=conversation_id,
        milestone_id=milestone_id,
    )
    key = new_storage_key(user.id, filename)
    storage = get_storage()
    storage.put(key, data, content_type)
    item = Attachment(
        uploader_id=user.id,
        project_id=parents["project_id"],
        contract_id=parents["contract_id"],
        conversation_id=parents["conversation_id"],
        milestone_id=parents["milestone_id"],
        filename=filename,
        storage_key=key,
        content_type=content_type,
        size=len(data),
        created_at=utcnow(),
    )
    db.add(item)
    db.flush()
    return item


def list_attachments(
    db: Session,
    user: User,
    *,
    project_id: int | None = None,
    contract_id: int | None = None,
    conversation_id: int | None = None,
    milestone_id: int | None = None,
) -> list[Attachment]:
    require_parent_access(
        db,
        user,
        project_id=project_id,
        contract_id=contract_id,
        conversation_id=conversation_id,
        milestone_id=milestone_id,
    )
    stmt = select(Attachment).options(joinedload(Attachment.uploader))
    filters = []
    if project_id is not None:
        filters.append(Attachment.project_id == project_id)
    if contract_id is not None:
        filters.append(Attachment.contract_id == contract_id)
    if conversation_id is not None:
        filters.append(Attachment.conversation_id == conversation_id)
    if milestone_id is not None:
        filters.append(Attachment.milestone_id == milestone_id)
    stmt = stmt.where(or_(*filters)).order_by(Attachment.created_at.desc(), Attachment.id.desc())
    return list(db.scalars(stmt).unique().all())


def delete_attachment(db: Session, user: User, attachment: Attachment) -> None:
    if not user_can_delete_attachment(db, user, attachment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    key = attachment.storage_key
    db.delete(attachment)
    db.flush()
    try:
        get_storage().delete(key)
    except Exception:  # noqa: BLE001 — metadata delete already committed by caller
        pass
