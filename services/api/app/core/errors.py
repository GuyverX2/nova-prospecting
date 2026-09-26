"""One error contract for the whole API.

Domain code raises :class:`~app.prospecting.service.ProspectingError`; the
transport layer turns it into ``{"detail": {"message": ..., "code": ...}}``.
Routes therefore contain no error translation, and every client sees the same
machine-readable ``code`` regardless of which endpoint failed.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger, get_request_id
from app.core.ratelimit import RateLimitExceeded
from app.prospecting.service import ProspectingError

logger = get_logger("nova.api")


def _payload(message: str, code: str) -> dict:
    body: dict[str, object] = {"detail": {"message": message, "code": code}}
    request_id = get_request_id()
    if request_id:
        body["request_id"] = request_id
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProspectingError)
    async def _prospecting_error(request: Request, exc: ProspectingError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "prospecting_error",
                extra={"code": exc.code, "path": request.url.path, "status": exc.status_code},
            )
        else:
            logger.info(
                "prospecting_rejected",
                extra={"code": exc.code, "path": request.url.path, "status": exc.status_code},
            )
        return JSONResponse(status_code=exc.status_code, content=_payload(exc.detail, exc.code))

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        logger.warning(
            "rate_limited", extra={"action": exc.action, "limit": exc.limit, "path": request.url.path}
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=_payload(
                f"Rate limit of {exc.limit} {exc.action} requests per minute exceeded",
                "RATE_LIMITED",
            ),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field paths help the caller; raw input values are not echoed back.
        fields = sorted({".".join(str(part) for part in error.get("loc", ())[1:]) for error in exc.errors()})
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                **_payload("Request validation failed", "REQUEST_VALIDATION_FAILED"),
                "fields": [field for field in fields if field],
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("database_error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_payload("The Nova database is unavailable", "DATABASE_UNAVAILABLE"),
        )
