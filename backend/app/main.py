import io
import shutil
import zipfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.models import ConvertRequest, InspectRequest
from app.recipe import env_text, env_values
from app.security import SafeError, parse_aws_env, reveal_target
from app.settings import ROOT, settings
from app.store import Store
from app.worker import Worker

ORIGINS = {"http://127.0.0.1:5175", "http://localhost:5175", "http://127.0.0.1:8011", "http://localhost:8011"}


def create_app(config=None, start_worker=True):
    config = config or settings()
    store = Store(config.state_dir)
    worker = Worker(store, config)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        yield
        worker.close()

    app = FastAPI(title="AWS to OCI Converter", lifespan=lifespan)
    app.state.store, app.state.worker = store, worker
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @app.middleware("http")
    async def local_requests(request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if (origin and origin not in ORIGINS) or request.headers.get("x-converter-request") != "1":
                return JSONResponse({"error": "Open the converter from its local UI."}, status_code=403)
            if int(request.headers.get("content-length", "0")) > 256000:
                return JSONResponse({"error": "Request exceeds the upload limit."}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        # Pydantic errors can contain submitted credentials; never serialize their input values.
        fields = [".".join(map(str, e["loc"][1:])) for e in exc.errors()]
        return JSONResponse({"error": "Check these fields: " + ", ".join(fields)}, status_code=422)

    @app.exception_handler(SafeError)
    async def safe_error(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"error": "Job not found."}, status_code=404)

    @app.get("/api/status")
    def status():
        return {
            "astra_configured": config.astra_configured,
            "astra_model": config.astra_model_id,
            "astra_provider": "OCI",
            "retention_hours": config.job_retention_hours,
            "scope": "local_single_user",
        }

    @app.post("/api/jobs", status_code=202)
    def inspect(body: InspectRequest):
        aws, ignored = parse_aws_env(body.aws_env)
        identifier = store.create(
            {
                "repository_url": body.repository_url,
                "source_branch": body.source_branch,
                "aws_components": aws,
                "ignored_env_values": ignored,
            },
            {"github_token": body.github_token.get_secret_value()},
        )
        return store.get(identifier)

    @app.get("/api/jobs")
    def jobs():
        return store.list()

    @app.get("/api/jobs/{identifier}")
    def job(identifier: str):
        return store.get(identifier)

    @app.post("/api/jobs/{identifier}/convert", status_code=202)
    def convert(identifier: str, body: ConvertRequest):
        try:
            body.validate_request()
            if not config.astra_configured:
                raise SafeError(
                    "OCI Astra is not configured yet. Add its details to the converter .env and restart the backend."
                )
            current = store.get(identifier)
            if current["status"] != "ready":
                raise SafeError("Inspect the repository before starting conversion.")
            if body.publish and not current.get("publish_allowed"):
                raise SafeError(
                    "Source branch workflows may trigger deployment. Choose download only or restrict those workflows first."
                )
            payload = store.secrets(identifier)
            payload.update(target=reveal_target(body.target), publish=body.publish)
            env_text(payload["target"])  # Validate serialization before queueing.
            store.queue_conversion(identifier, payload)
            return store.get(identifier)
        except ValueError as exc:
            raise SafeError(str(exc)) from exc

    @app.delete("/api/jobs/{identifier}")
    def delete_job(identifier: str):
        directory = worker.directory(identifier)  # Validate the resolved workspace boundary.

        def remove_workspace():
            if directory.exists():
                shutil.rmtree(directory)

        try:
            store.delete(identifier, remove_workspace)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(409, "Local files are in use. Close downloads and retry deletion.") from exc
        return {"deleted": identifier}

    @app.post("/api/jobs/{identifier}/cancel")
    def cancel(identifier: str):
        store.cancel(identifier)
        return store.get(identifier)

    @app.get("/api/jobs/{identifier}/environment")
    def environment(identifier: str):
        current = store.get(identifier)
        try:
            target = store.secrets(identifier).get("target")
        except ValueError:
            target = None
        oracle = None
        masked = []
        if target is not None:
            # Mask before serialization. The browser never receives these secrets.
            preview = dict(target)
            for key, variable in (("db_password", "OCI_DB_PASSWORD"),
                                  ("db_wallet_password", "OCI_DB_WALLET_PASSWORD")):
                if preview.get(key):
                    preview[key] = "[REDACTED]"
                    masked.append(variable)
            preview["private_key"] = bool(preview.get("private_key"))
            oracle = env_values(preview)
        return {
            "aws": current.get("aws_components", {}),
            "aws_ignored": current.get("ignored_env_values", 0),
            "oci": oracle,
            "masked": masked,
            "status": current["status"],
        }

    @app.get("/api/jobs/{identifier}/configuration")
    def configuration(identifier: str):
        current = store.get(identifier)
        if current["status"] != "completed":
            raise HTTPException(409, "Configuration is available after successful conversion.")
        target = store.secrets(identifier)["target"]
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(".env", env_text(target))
            if target.get("private_key"):
                profile = target["oci_profile"]
                identity = {
                    "user": target["user_id"],
                    "tenancy": target["tenancy_id"],
                    "fingerprint": target["fingerprint"],
                    "region": target["region"],
                    "key_file": "config/oci/api_key.pem",
                }
                if any("\n" in value or "\r" in value for value in [profile, *identity.values()]):
                    raise SafeError("Invalid OCI credential configuration.")
                archive.writestr(
                    "config/oci/config",
                    "[" + profile + "]\n" + "\n".join(f"{k}={v}" for k, v in identity.items()),
                )
                archive.writestr("config/oci/api_key.pem", target["private_key"])
        return Response(
            data.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="oci-private-configuration.zip"'},
        )

    @app.get("/api/jobs/{identifier}/source")
    def download(identifier: str):
        if store.get(identifier)["status"] != "completed":
            raise HTTPException(409, "Code is available after successful conversion.")
        output = worker.directory(identifier) / "output"
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in output.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(output).as_posix())
        return Response(
            data.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="oci-project.zip"'},
        )

    @app.get("/{path:path}")
    def frontend(path: str):
        root = (ROOT / "frontend" / "dist").resolve()
        candidate = (root / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        if (root / "index.html").is_file():
            return FileResponse(root / "index.html")
        return JSONResponse({"message": "Start the frontend on port 5175, or build frontend/dist."})

    return app


app = create_app()
