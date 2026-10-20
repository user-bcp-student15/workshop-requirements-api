import base64
import asyncio
import json
import time
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import (
    MAX_UPLOAD_REQUEST_SIZE,
    MAX_UPLOAD_SIZE,
    UploadBodyLimitMiddleware,
    create_app,
)

TEST_SECRET = "workshop-test-secret-32-bytes-minimum-value"


def token(
    username: str = "student",
    role: str = "STUDENT",
    *,
    secret: str = TEST_SECRET,
    expires_at: int | None = None,
) -> str:
    now = int(time.time())
    claims = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": expires_at if expires_at is not None else now + 3600,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def headers(username: str = "student", role: str = "STUDENT") -> dict[str, str]:
    return {"Authorization": f"Bearer {token(username, role)}"}


def test_lists_seeded_tasks(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        response = client.get("/api/tasks", headers=headers())
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_creates_task_with_sql_characters_and_summarizes(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            headers=headers(),
            json={
                "title": "O'Reilly's tests",
                "description": "Keep 'quoted' text",
                "status": "TODO",
                "priority": "HIGH",
            },
        )
        summary = client.get("/api/summary", headers=headers())
    assert created.status_code == 201
    assert created.json()["title"] == "O'Reilly's tests"
    assert created.json()["owner"] == "student"
    assert summary.json()["total"] == 3


def test_task_queries_treat_owner_as_a_literal_value(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    injected_owner = "student' OR '1'='1"
    with TestClient(app) as client:
        tasks = client.get("/api/tasks", headers=headers(injected_owner), params={"owner": injected_owner})
        summary = client.get("/api/summary", headers=headers(injected_owner), params={"owner": injected_owner})
    assert tasks.status_code == 200
    assert tasks.json() == []
    assert summary.status_code == 200
    assert summary.json()["total"] == 0


def test_task_endpoints_enforce_self_only_owner_policy(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        listed = client.get("/api/tasks", headers=headers(), params={"owner": "trainer"})
        summary = client.get("/api/summary", headers=headers(), params={"owner": "trainer"})
        created = client.post(
            "/api/tasks",
            headers=headers(),
            json={"title": "Not permitted", "owner": "trainer"},
        )
    assert listed.status_code == 403
    assert summary.status_code == 403
    assert created.status_code == 403


def test_uploads_requirement(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    app = create_app(str(tmp_path / "workshop.db"), str(upload_dir))
    with TestClient(app) as client:
        response = client.post(
            "/api/requirements",
            headers=headers(),
            files={"file": ("requirements.txt", b"Login must be accessible", "text/plain")},
        )
    assert response.status_code == 201
    assert response.json()["size"] == len(b"Login must be accessible")
    assert (upload_dir / "requirements.txt").read_bytes() == b"Login must be accessible"


def test_upload_accepts_file_at_exact_size_limit(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    app = create_app(str(tmp_path / "workshop.db"), str(upload_dir))
    content = b"x" * MAX_UPLOAD_SIZE
    with TestClient(app) as client:
        response = client.post(
            "/api/requirements",
            headers=headers(),
            files={"file": ("maximum.txt", content, "text/plain")},
        )
    assert response.status_code == 201
    assert response.json()["size"] == MAX_UPLOAD_SIZE
    assert (upload_dir / "maximum.txt").stat().st_size == MAX_UPLOAD_SIZE


@pytest.mark.parametrize("filename", ["../outside.txt", "..\\outside.txt", ".", ".."])
def test_upload_rejects_unsafe_filenames(tmp_path: Path, filename: str) -> None:
    upload_dir = tmp_path / "uploads"
    app = create_app(str(tmp_path / "workshop.db"), str(upload_dir))
    with TestClient(app) as client:
        response = client.post(
            "/api/requirements",
            headers=headers(),
            files={"file": (filename, b"content", "text/plain")},
        )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid file name"}
    assert (tmp_path / "workshop.db").exists()
    assert list(upload_dir.iterdir()) == []


def test_windows_path_filename_is_reduced_to_a_safe_basename(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    app = create_app(str(tmp_path / "workshop.db"), str(upload_dir))
    with TestClient(app) as client:
        response = client.post(
            "/api/requirements",
            headers=headers(),
            files={"file": ("C:\\temp\\outside.txt", b"content", "text/plain")},
        )
    assert response.status_code == 201
    assert response.json()["fileName"] == "outside.txt"
    assert (upload_dir / "outside.txt").read_bytes() == b"content"
    assert not (tmp_path.parent / "outside.txt").exists()


def test_upload_rejects_oversized_file_without_writing(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    app = create_app(str(tmp_path / "workshop.db"), str(upload_dir))
    with TestClient(app) as client:
        response = client.post(
            "/api/requirements",
            headers=headers(),
            files={"file": ("large.txt", b"x" * (MAX_UPLOAD_SIZE + 1), "text/plain")},
        )
    assert response.status_code == 413
    assert response.json() == {"detail": "File exceeds 10 MiB limit"}
    assert list(upload_dir.iterdir()) == []


def test_upload_request_body_limit_rejects_before_multipart_parsing(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    app = create_app(str(tmp_path / "workshop.db"), str(upload_dir))
    with TestClient(app) as client:
        response = client.post(
            "/api/requirements",
            headers={**headers(), "Content-Type": "multipart/form-data; boundary=oversized"},
            content=b"x" * (MAX_UPLOAD_REQUEST_SIZE + 1),
        )
    assert response.status_code == 413
    assert response.json() == {"detail": "File exceeds 10 MiB limit"}
    assert list(upload_dir.iterdir()) == []


def test_upload_body_limit_rejects_chunked_request_without_content_length() -> None:
    sent: list[dict[str, object]] = []
    chunks = iter(
        [
            {
                "type": "http.request",
                "body": b"x" * (MAX_UPLOAD_REQUEST_SIZE // 2),
                "more_body": True,
            },
            {
                "type": "http.request",
                "body": b"x" * (MAX_UPLOAD_REQUEST_SIZE // 2 + 1),
                "more_body": True,
            },
        ]
    )
    downstream_called = False

    async def receive() -> dict[str, object]:
        return next(chunks)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    async def downstream(scope: dict[str, object], receive: object, send: object) -> None:
        nonlocal downstream_called
        downstream_called = True

    middleware = UploadBodyLimitMiddleware(downstream, MAX_UPLOAD_REQUEST_SIZE)
    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/requirements",
                "headers": [(b"content-type", b"multipart/form-data; boundary=oversized")],
            },
            receive,
            send,
        )
    )

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    assert response_start["status"] == 413
    assert json.loads(response_body) == {"detail": "File exceeds 10 MiB limit"}
    assert not downstream_called


def test_upload_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    existing = upload_dir / "requirements.txt"
    existing.write_bytes(b"original")
    app = create_app(str(tmp_path / "workshop.db"), str(upload_dir))
    with TestClient(app) as client:
        response = client.post(
            "/api/requirements",
            headers=headers(),
            files={"file": ("requirements.txt", b"replacement", "text/plain")},
        )
    assert response.status_code == 400
    assert response.json() == {"detail": "File already exists"}
    assert existing.read_bytes() == b"original"


def test_rejects_expired_jwt(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    expired = token(expires_at=int(time.time()) - 1)
    with TestClient(app) as client:
        response = client.get("/api/tasks", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_rejects_jwt_with_altered_claims(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    parts = token().split(".")
    padding = "=" * (-len(parts[1]) % 4)
    claims = json.loads(base64.urlsafe_b64decode(parts[1] + padding))
    claims["role"] = "TRAINER"
    parts[1] = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).decode().rstrip("=")
    with TestClient(app) as client:
        response = client.get("/api/tasks", headers={"Authorization": "Bearer " + ".".join(parts)})
    assert response.status_code == 401


def test_rejects_token_signed_with_another_secret(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    invalid = token(secret="different-test-secret-32-bytes-long")
    with TestClient(app) as client:
        response = client.get("/api/tasks", headers={"Authorization": f"Bearer {invalid}"})
    assert response.status_code == 401


def test_rejects_legacy_base64_token(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    legacy = base64.b64encode(b"student|STUDENT|9999999999|WORKSHOP_SECRET_2026").decode()
    with TestClient(app) as client:
        response = client.get("/api/tasks", headers={"Authorization": f"Bearer {legacy}"})
    assert response.status_code == 401


def test_rejects_missing_bearer_token(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        response = client.get("/api/tasks")
    assert response.status_code == 401
