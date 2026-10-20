# Workshop Requirements API — Python FastAPI

> **Laboratorio intencionalmente vulnerable.** Ejecutar únicamente en local, repositorios privados y ambientes aislados. No publicar en Internet ni desplegar en CERT/PROD.

API FastAPI que administra tareas del workshop y recibe archivos de requerimientos. Usa SQLite y consume el token emitido por el backend Quarkus.

## Ejecución

Requisitos: Python 3.13.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Swagger: `http://localhost:8000/docs`

## Endpoints

- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/summary`
- `POST /api/requirements`
- `GET /api/backend-health`

Set `AUTH_TOKEN_SECRET` to the same secret used by the auth backend; it must contain at least 32 UTF-8 bytes. The API accepts signed HS256 JWTs only and rejects the legacy Base64 token format.

Task list, summary, and creation are scoped to the authenticated username. Supplying a different owner returns `403`. Requirement uploads accept basenames only, do not overwrite existing files, and are limited to 10 MiB. The request body is bounded before multipart parsing; invalid names or collisions return `400`, and oversized files return `413`.

Fuera de estos controles permanecen deuda del laboratorio, incluida la conexión global SQLite y CORS permisivo. Esta API sigue destinada exclusivamente a entornos aislados; revisar `RETO.md` antes de cualquier despliegue.
