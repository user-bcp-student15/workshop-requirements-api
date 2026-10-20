from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import jwt
import urllib3
from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from jwt import InvalidTokenError
from starlette.responses import JSONResponse

JWT_ALGORITHM = "HS256"
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_MULTIPART_OVERHEAD = 64 * 1024
MAX_UPLOAD_REQUEST_SIZE = MAX_UPLOAD_SIZE + MAX_MULTIPART_OVERHEAD
JWT_SECRET = os.getenv("AUTH_TOKEN_SECRET")
if not JWT_SECRET or len(JWT_SECRET.encode("utf-8")) < 32:
    raise RuntimeError("AUTH_TOKEN_SECRET must be configured with at least 32 UTF-8 bytes")


class UploadBodyLimitMiddleware:
    def __init__(self, app: Any, max_request_size: int) -> None:
        self.app = app
        self.max_request_size = max_request_size

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/api/requirements":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_request_size:
                    await JSONResponse(
                        {"detail": "File exceeds 10 MiB limit"},
                        status_code=413,
                    )(scope, receive, send)
                    return
            except ValueError:
                pass

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_request_size:
                await JSONResponse(
                    {"detail": "File exceeds 10 MiB limit"},
                    status_code=413,
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_body() -> dict[str, Any]:
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay_body, send)


def legacy_identity(authorization: str = Header(default="")) -> dict[str, str]:
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token or " " in token:
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
        username = claims["sub"]
        role = claims["role"]
        if not isinstance(username, str) or not username or not isinstance(role, str) or not role:
            raise InvalidTokenError("Invalid identity claims")
        return {"username": username, "role": role}
    except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=401, detail="Invalid token") from error


def require_self_owner(identity: dict[str, str], owner: str) -> None:
    if owner != identity["username"]:
        raise HTTPException(status_code=403, detail="Forbidden")


def create_app(db_path: str | None = None, upload_dir: str | None = None) -> FastAPI:
    selected_db = db_path or os.getenv("WORKSHOP_DB_PATH", "./data/workshop.db")
    selected_uploads = upload_dir or os.getenv("WORKSHOP_UPLOAD_DIR", "./uploads")
    Path(selected_db).parent.mkdir(parents=True, exist_ok=True)
    Path(selected_uploads).mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(selected_db, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL, owner TEXT NOT NULL, priority TEXT NOT NULL, created_at TEXT NOT NULL)")
    count = connection.execute("SELECT COUNT(*) AS total FROM tasks").fetchone()["total"]
    if count == 0:
        connection.execute("INSERT INTO tasks(title,description,status,owner,priority,created_at) VALUES ('Refactor login','Separar responsabilidades en frontend','TODO','student','HIGH',datetime('now'))")
        connection.execute("INSERT INTO tasks(title,description,status,owner,priority,created_at) VALUES ('Review API','Revisar seguridad de endpoints','IN_PROGRESS','student','MEDIUM',datetime('now'))")
        connection.execute("INSERT INTO tasks(title,description,status,owner,priority,created_at) VALUES ('Trainer notes','Preparar retrospectiva','TODO','trainer','LOW',datetime('now'))")
        connection.commit()

    app = FastAPI(title="Workshop Requirements API", version="0.1.0")
    app.state.connection = connection
    app.state.upload_dir = selected_uploads
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(UploadBodyLimitMiddleware, max_request_size=MAX_UPLOAD_REQUEST_SIZE)

    def as_task(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "owner": row["owner"],
            "priority": row["priority"],
            "createdAt": row["created_at"],
        }

    @app.get("/api/tasks")
    def list_tasks(owner: str | None = Query(default=None), identity: dict[str, str] = Depends(legacy_identity)) -> list[dict[str, Any]]:
        requested_owner = owner or identity["username"]
        require_self_owner(identity, requested_owner)
        rows = connection.execute(
            "SELECT id,title,description,status,owner,priority,created_at FROM tasks WHERE owner=? ORDER BY id",
            (requested_owner,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(as_task(row))
        return result

    @app.post("/api/tasks", status_code=201)
    def create_task(payload: dict[str, Any] = Body(...), identity: dict[str, str] = Depends(legacy_identity)) -> dict[str, Any]:
        title = str(payload.get("title", ""))
        description = str(payload.get("description", ""))
        status = str(payload.get("status", "TODO"))
        priority = str(payload.get("priority", "MEDIUM"))
        owner = str(payload.get("owner", identity["username"]))
        require_self_owner(identity, owner)
        cursor = connection.execute(
            "INSERT INTO tasks(title,description,status,owner,priority,created_at) VALUES (?,?,?,?,?,datetime('now'))",
            (title, description, status, owner, priority),
        )
        connection.commit()
        row = connection.execute(
            "SELECT id,title,description,status,owner,priority,created_at FROM tasks WHERE id=?",
            (cursor.lastrowid,),
        ).fetchone()
        return as_task(row)

    @app.get("/api/summary")
    def summary(owner: str | None = Query(default=None), identity: dict[str, str] = Depends(legacy_identity)) -> dict[str, Any]:
        requested_owner = owner or identity["username"]
        require_self_owner(identity, requested_owner)
        rows = connection.execute(
            "SELECT status,priority FROM tasks WHERE owner=?",
            (requested_owner,),
        ).fetchall()
        response: dict[str, Any] = {"owner": requested_owner, "total": 0, "byStatus": {}, "highPriorityOpen": 0}
        for row in rows:
            response["total"] = response["total"] + 1
            if row["status"] in response["byStatus"]:
                response["byStatus"][row["status"]] = response["byStatus"][row["status"]] + 1
            else:
                response["byStatus"][row["status"]] = 1
            if row["priority"] == "HIGH":
                if row["status"] != "DONE":
                    if row["status"] != "ARCHIVED":
                        response["highPriorityOpen"] = response["highPriorityOpen"] + 1
        return response

    @app.post("/api/requirements", status_code=201)
    async def upload_requirement(file: UploadFile = File(...), identity: dict[str, str] = Depends(legacy_identity)) -> dict[str, Any]:
        filename = file.filename or ""
        if (
            filename in {"", ".", ".."}
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
            or Path(filename).name != filename
        ):
            raise HTTPException(status_code=400, detail="Invalid file name")

        content = await file.read(MAX_UPLOAD_SIZE + 1)
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds 10 MiB limit")

        target = Path(selected_uploads) / filename
        try:
            with target.open("xb") as destination:
                destination.write(content)
        except FileExistsError as error:
            raise HTTPException(status_code=400, detail="File already exists") from error
        return {"owner": identity["username"], "fileName": filename, "storedAt": str(target), "size": len(content)}

    @app.get("/api/backend-health")
    def backend_health(identity: dict[str, str] = Depends(legacy_identity)) -> dict[str, Any]:
        url = os.getenv("AUTH_HEALTH_URL", "http://localhost:8080/q/health")
        try:
            response = urllib3.PoolManager().request("GET", url, timeout=3.0)
            return {"requestedBy": identity["username"], "status": response.status, "body": response.data.decode("utf-8")}
        except Exception as error:
            return {"requestedBy": identity["username"], "status": 0, "body": str(error)}

    @app.on_event("shutdown")
    def close_connection() -> None:
        connection.close()

    return app


app = create_app()
