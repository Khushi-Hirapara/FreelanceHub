"""Secure attachments use object storage keys, not database blobs."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
import app.storage as storage_module

PASSWORD = "Testpass1"
COVER = "I can deliver this work clearly and keep the client updated throughout."
client = TestClient(app)
settings = get_settings()
root = Path(settings.storage_local_root) / f"test-{uuid.uuid4().hex}"
root.mkdir(parents=True, exist_ok=True)
settings.storage_provider = "local"
settings.storage_local_root = str(root)
storage_module._storage = None


def _register(role: str) -> dict:
    stamp = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/auth/register",
        json={
            "name": f"{role} {stamp}",
            "email": f"{role}-{stamp}@example.com",
            "password": PASSWORD,
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"token": body["access_token"], "user": body["user"]}


def _headers(actor: dict) -> dict:
    return {"Authorization": f"Bearer {actor['token']}"}


def test_attachment_upload_download_and_authz():
    owner = _register("client")
    worker = _register("freelancer")
    outsider = _register("client")

    project = client.post(
        "/api/projects",
        headers=_headers(owner),
        json={
            "title": "Attachment brief",
            "category": "Web Dev",
            "description": "A brief used only to exercise secure file uploads.",
            "skills": ["Python"],
            "budget_min": 100,
            "budget_max": 400,
        },
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    proposal = client.post(
        "/api/proposals",
        headers=_headers(worker),
        json={
            "project_id": project_id,
            "bid_amount": 200,
            "cover_letter": COVER,
            "estimated_duration": "1 week",
        },
    )
    assert proposal.status_code == 201, proposal.text

    upload = client.post(
        "/api/attachments",
        headers=_headers(owner),
        files={"file": ("brief.pdf", io.BytesIO(b"%PDF-1.4 demo"), "application/pdf")},
        data={"project_id": str(project_id)},
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["filename"] == "brief.pdf"
    assert "storage_key" not in body
    assert body["project_id"] == project_id
    attachment_id = body["id"]

    listed = client.get(f"/api/attachments?project_id={project_id}", headers=_headers(worker))
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == attachment_id

    denied = client.get(f"/api/attachments?project_id={project_id}", headers=_headers(outsider))
    assert denied.status_code == 403

    download = client.get(f"/api/attachments/{attachment_id}/download", headers=_headers(worker))
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    assert "storage_key" not in download.headers.get("content-disposition", "").lower()

    blocked = client.get(f"/api/attachments/{attachment_id}/download", headers=_headers(outsider))
    assert blocked.status_code == 403

    bad_type = client.post(
        "/api/attachments",
        headers=_headers(owner),
        files={"file": ("hack.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        data={"project_id": str(project_id)},
    )
    assert bad_type.status_code == 400

    path_probe = client.post(
        "/api/attachments",
        headers=_headers(owner),
        files={"file": ("../../secret.txt", io.BytesIO(b"nope"), "text/plain")},
        data={"project_id": str(project_id)},
    )
    assert path_probe.status_code == 201
    assert path_probe.json()["filename"] == "secret.txt"
    assert ".." not in path_probe.json()["filename"]

    deleted = client.delete(f"/api/attachments/{attachment_id}", headers=_headers(outsider))
    assert deleted.status_code == 403

    removed = client.delete(f"/api/attachments/{attachment_id}", headers=_headers(owner))
    assert removed.status_code == 204
    assert client.get(f"/api/attachments/{attachment_id}", headers=_headers(owner)).status_code == 404


if __name__ == "__main__":
    test_attachment_upload_download_and_authz()
    print("ok")
