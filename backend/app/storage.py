"""Object storage for attachments. Files never go in PostgreSQL."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".txt",
    ".md",
    ".csv",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
}

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}

EXTENSION_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".md": {"text/plain", "text/markdown", "application/octet-stream"},
    ".csv": {"text/csv", "text/plain", "application/octet-stream"},
    ".doc": {"application/msword", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
    ".xls": {"application/vnd.ms-excel", "application/octet-stream"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    },
    ".ppt": {"application/vnd.ms-powerpoint", "application/octet-stream"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/octet-stream",
    },
    ".zip": {"application/zip", "application/x-zip-compressed", "application/octet-stream"},
}


def sanitize_filename(name: str | None) -> str:
    raw = (name or "file").strip().replace("\\", "/").split("/")[-1]
    cleaned = SAFE_NAME.sub("_", raw).strip("._") or "file"
    return cleaned[:180]


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_upload(filename: str, content_type: str | None, size: int) -> tuple[str, str]:
    settings = get_settings()
    if size <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty files are not allowed")
    if size > settings.attachment_max_bytes:
        limit_mb = settings.attachment_max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the {limit_mb} MB limit",
        )
    safe_name = sanitize_filename(filename)
    ext = extension_of(safe_name)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File type is not allowed")
    mime = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    if mime not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content type is not allowed")
    allowed_for_ext = EXTENSION_CONTENT_TYPES.get(ext, set())
    if mime not in allowed_for_ext and mime != "application/octet-stream":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File type does not match content type")
    return safe_name, mime


def new_storage_key(uploader_id: int, filename: str) -> str:
    ext = extension_of(filename)
    token = uuid.uuid4().hex
    return f"attachments/{uploader_id}/{token}{ext}"


class StorageBackend:
    def put(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class LocalObjectStorage(StorageBackend):
    """Filesystem object store. Same key interface as S3; not a public web root."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in key.replace("\\", "/").split("/"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid storage key")
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid storage key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        _ = content_type

    def get(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in storage")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.is_file():
            path.unlink()


class S3ObjectStorage(StorageBackend):
    def __init__(self):
        settings = get_settings()
        try:
            import boto3
            from botocore.client import Config
        except ImportError as exc:
            raise RuntimeError("boto3 is required for STORAGE_PROVIDER=s3") from exc
        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET is required when STORAGE_PROVIDER=s3")
        kwargs = {
            "service_name": "s3",
            "region_name": settings.s3_region,
            "aws_access_key_id": settings.s3_access_key or None,
            "aws_secret_access_key": settings.s3_secret_key or None,
            "config": Config(signature_version="s3v4"),
        }
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        self.client = boto3.client(**kwargs)
        self.bucket = settings.s3_bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ACL="private",
        )

    def get(self, key: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001 — map provider errors to 404
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in storage") from exc
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is not None:
        return _storage
    settings = get_settings()
    provider = (settings.storage_provider or "local").strip().lower()
    if provider == "s3":
        _storage = S3ObjectStorage()
    elif provider == "local":
        _storage = LocalObjectStorage(settings.storage_local_root)
    else:
        raise RuntimeError(f"Unsupported STORAGE_PROVIDER: {provider}")
    return _storage


async def read_upload(file: UploadFile) -> tuple[str, str, bytes]:
    settings = get_settings()
    raw_name = file.filename or "file"
    data = await file.read(settings.attachment_max_bytes + 1)
    if len(data) > settings.attachment_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the {settings.attachment_max_bytes // (1024 * 1024)} MB limit",
        )
    safe_name, mime = validate_upload(raw_name, file.content_type, len(data))
    return safe_name, mime, data


def content_disposition(filename: str) -> str:
    ascii_name = sanitize_filename(filename).encode("ascii", "ignore").decode() or "file"
    utf8_name = quote(filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
