from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.attachment_flow import (
    create_attachment,
    delete_attachment,
    list_attachments,
    user_can_access_attachment,
)
from app.database import get_db
from app.deps import get_current_user
from app.models import Attachment, User
from app.schemas import AttachmentOut
from app.storage import content_disposition, get_storage, read_upload
from sqlalchemy import select

router = APIRouter(prefix="/attachments", tags=["Attachments"])


def serialize_attachment(item: Attachment) -> AttachmentOut:
    return AttachmentOut(
        id=item.id,
        uploader_id=item.uploader_id,
        project_id=item.project_id,
        contract_id=item.contract_id,
        conversation_id=item.conversation_id,
        milestone_id=item.milestone_id,
        filename=item.filename,
        content_type=item.content_type,
        size=item.size,
        created_at=item.created_at,
        uploader_name=item.uploader.name if item.uploader else None,
    )


def load_attachment(db: Session, attachment_id: int) -> Attachment:
    item = db.scalars(
        select(Attachment).options(joinedload(Attachment.uploader)).where(Attachment.id == attachment_id)
    ).unique().first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return item


@router.get("", response_model=list[AttachmentOut])
def get_attachments(
    project_id: int | None = None,
    contract_id: int | None = None,
    conversation_id: int | None = None,
    milestone_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = list_attachments(
        db,
        current_user,
        project_id=project_id,
        contract_id=contract_id,
        conversation_id=conversation_id,
        milestone_id=milestone_id,
    )
    return [serialize_attachment(item) for item in rows]


@router.post("", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    request: Request,
    file: UploadFile = File(...),
    project_id: int | None = Form(default=None),
    contract_id: int | None = Form(default=None),
    conversation_id: int | None = Form(default=None),
    milestone_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.config import get_settings
    from app.rate_limit import enforce_rate_limit

    settings = get_settings()
    enforce_rate_limit(request, bucket="upload", limit=settings.rate_limit_upload_per_minute)
    filename, content_type, data = await read_upload(file)
    item = create_attachment(
        db,
        current_user,
        filename=filename,
        content_type=content_type,
        data=data,
        project_id=project_id,
        contract_id=contract_id,
        conversation_id=conversation_id,
        milestone_id=milestone_id,
    )
    db.commit()
    return serialize_attachment(load_attachment(db, item.id))


@router.get("/{attachment_id}", response_model=AttachmentOut)
def get_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = load_attachment(db, attachment_id)
    if not user_can_access_attachment(db, current_user, item):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return serialize_attachment(item)


@router.get("/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = load_attachment(db, attachment_id)
    if not user_can_access_attachment(db, current_user, item):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    # Never return the storage key. Stream bytes only after authorization.
    data = get_storage().get(item.storage_key)
    return Response(
        content=data,
        media_type=item.content_type,
        headers={
            "Content-Disposition": content_disposition(item.filename),
            "Content-Length": str(item.size),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = load_attachment(db, attachment_id)
    delete_attachment(db, current_user, item)
    db.commit()
