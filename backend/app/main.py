import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.integration import IntegrationLimiter
from app.api.integration import router as integration_router
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.dependencies import Container, build_container
from app.domain.errors import AppError
from app.observability.logging import configure_logging, request_id

log = logging.getLogger(__name__)


def error_response(code: str, message: str, status: int):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id.get()}},
    )


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        configure_logging(settings.log_level)
        app.state.container = container or build_container(settings)
        log.info("application_started")
        try:
            yield
        finally:
            if app.state.container.engine is not None:
                app.state.container.engine.dispose()
            log.info("application_stopped")

    app = FastAPI(title="Distributor Aggregator", version="2.0.0", lifespan=lifespan)
    app.state.integration_limiter = IntegrationLimiter(settings.integration_requests_per_minute, settings.integration_max_concurrent)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        token = request_id.set(str(uuid4()))
        start = perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                log.error("unhandled_api_failure", extra={"error_type": type(exc).__name__})
                response = error_response("internal_error", "The request could not be completed.", 500)
            response.headers["X-Request-ID"] = request_id.get()
            response.headers["Cache-Control"] = "no-store"
            if response.status_code == 429:
                response.headers["Retry-After"] = "60"
            if response.status_code == 401:
                response.headers["WWW-Authenticate"] = "Bearer"
            log.info(
                "api_request",
                extra={
                    "operation": request.method,
                    "status": response.status_code,
                    "latency_ms": int((perf_counter() - start) * 1000),
                },
            )
            return response
        finally:
            request_id.reset(token)

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        log.warning("api_failure", extra={"error_type": exc.code, "status": exc.status_code})
        return error_response(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(
            "validation_error", "Check required fields, question length, and pagination values.", 422
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        log.error("database_failure", extra={"error_type": type(exc).__name__})
        return error_response("database_unavailable", "The database is unavailable. Please try again.", 503)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(
            "http_error", "The requested operation could not be completed.", exc.status_code
        )

    app.include_router(router)
    app.include_router(integration_router)
    return app


app = create_app()
