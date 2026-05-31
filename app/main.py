"""
app/main.py
Application factory — the single entry point for the FastAPI app.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import PlayerOnePayError
from app.core.logging import configure_logging, get_logger
from app.middleware.request_id import RequestIDMiddleware

settings = get_settings()
log = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Runs at startup and shutdown."""
    configure_logging()
    log.info("app.starting", version=settings.APP_VERSION, env=settings.APP_ENV)

    # Initialise DB tables (dev/test only — prod uses Alembic migrations)
    if not settings.is_production:
        from app.db.session import engine
        from app.db.base import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("db.tables_created")

    # Sentry (production error tracking)
    if settings.SENTRY_DSN and settings.is_production:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.2)
        log.info("sentry.initialised")

    yield

    log.info("app.shutdown")
    from app.db.session import engine
    await engine.dispose()


# ── Factory ───────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "PlayerOnePay v2 — production-grade payment API. "
            "All endpoints are versioned under `/api/v1`."
        ),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost registered = outermost executed) ─
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-ms"],
    )
    app.add_middleware(RequestIDMiddleware)

    # ── Exception Handlers ────────────────────────────────────────────────────

    @app.exception_handler(PlayerOnePayError)
    async def domain_error_handler(request: Request, exc: PlayerOnePayError) -> JSONResponse:
        log.warning(
            "domain_error",
            error_code=exc.error_code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error_code": exc.error_code,
                "message": exc.message,
                "detail": exc.detail,
                "request_id": request.headers.get("X-Request-ID"),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error_code": "validation_error",
                "message": "Request validation failed.",
                "detail": exc.errors(),
                "request_id": request.headers.get("X-Request-ID"),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_exception", exc_info=exc, path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error_code": "internal_error",
                "message": "An unexpected error occurred. Please try again.",
                "request_id": request.headers.get("X-Request-ID"),
            },
        )

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # ── Health / Readiness probes ─────────────────────────────────────────────
    @app.get("/health", tags=["Observability"], include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.get("/ready", tags=["Observability"], include_in_schema=False)
    async def ready(request: Request) -> dict:
        from app.db.session import engine
        try:
            async with engine.connect():
                pass
            db_ok = True
        except Exception:
            db_ok = False
        ready = db_ok
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "not_ready", "db": db_ok},
        )

    @app.get("/", tags=["Root"], include_in_schema=False)
    async def root() -> dict:
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
