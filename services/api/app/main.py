"""Nova application entrypoint: wiring only, no business logic."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, metrics
from app.db.bootstrap import ensure_schema
from app.db.session import engine
from app.prospecting import models  # noqa: F401 -- registers Nova-owned tables
from app.prospecting.api.routes import public_router, router
from app.tenancy import service  # noqa: F401 -- registers the audit table

logger = get_logger("nova.main")

API_PREFIX = "/api/v1"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _spa_directory() -> Path | None:
    candidate = Path(settings.SPA_DIST_DIR)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate if (candidate / "index.html").is_file() else None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings.validate()
    for advisory in settings.warnings():
        logger.warning("nova_configuration_advisory", extra={"advisory": advisory})
    if settings.DB_AUTO_CREATE:
        # Convenience for local/dev and the single-container image. Managed
        # environments run `alembic upgrade head` instead; see README. Either
        # way the database ends up stamped, so it stays upgradable.
        logger.info("nova_db_bootstrap", extra={"outcome": ensure_schema(engine)})
    logger.info("nova_startup", extra=settings.safe_summary())
    try:
        yield
    finally:
        engine.dispose()
        logger.info("nova_shutdown")


app = FastAPI(
    title="Nova",
    version="1.0.0",
    description=(
        "Evidence-first website prospecting: audit a public page, generate a versioned "
        "proposal, require human approval, then share or deliver it under an operator kill switch."
    ),
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
if settings.CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.CORS_ALLOW_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

register_exception_handlers(app)
app.include_router(router, prefix=API_PREFIX)
app.include_router(public_router, prefix=API_PREFIX)


@app.get("/health/live", tags=["health"], summary="Liveness probe")
def health_live() -> dict:
    """Process is up. Never touches the database."""
    return {"status": "ok", "service": "nova"}


@app.get("/health/ready", tags=["health"], summary="Readiness probe")
def health_ready(response: Response) -> dict:
    """Ready to serve traffic: configuration is valid and the database answers."""
    checks: dict[str, str] = {}
    ready = True
    try:
        settings.validate()
        checks["config"] = "ok"
    except Exception as exc:
        ready = False
        checks["config"] = str(exc)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        ready = False
        checks["database"] = "unavailable"
        logger.exception("readiness_database_check_failed")
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
        "warnings": settings.warnings(),
        **settings.safe_summary(),
    }


@app.get("/metrics", tags=["health"], summary="Prometheus text metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"], include_in_schema=False)
def unknown_api_route(path: str) -> JSONResponse:
    """Unknown API paths stay JSON even when the SPA is mounted at the root."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": {"message": "Unknown API route", "code": "ROUTE_NOT_FOUND"}},
    )


_spa = _spa_directory()
if _spa is not None:
    # Same-origin hosting: the browser talks to /api/v1 without CORS.
    app.mount("/", StaticFiles(directory=str(_spa), html=True), name="nova-spa")
