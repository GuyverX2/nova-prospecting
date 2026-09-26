"""Request correlation, access logging and in-process request metrics."""
from __future__ import annotations

import time
from collections import Counter
from collections.abc import Awaitable, Callable
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, reset_request_id, set_request_id

REQUEST_ID_HEADER = "X-Request-ID"
logger = get_logger("nova.access")


class RequestMetrics:
    """Tiny in-process counter set exposed on ``/metrics``.

    Deliberately label-poor: method, route template and status class only. No
    tenant, path parameter or user value ever becomes a metric label.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: Counter[tuple[str, str, str]] = Counter()
        self._duration_ms: Counter[tuple[str, str]] = Counter()
        self._in_flight = 0

    def start(self) -> None:
        with self._lock:
            self._in_flight += 1

    def observe(self, method: str, route: str, status_code: int, duration_ms: float) -> None:
        bucket = f"{status_code // 100}xx"
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._requests[(method, route, bucket)] += 1
            self._duration_ms[(method, route)] += int(duration_ms)

    def render(self) -> str:
        with self._lock:
            requests = dict(self._requests)
            durations = dict(self._duration_ms)
            in_flight = self._in_flight
        lines = [
            "# HELP nova_http_requests_total HTTP requests handled by Nova.",
            "# TYPE nova_http_requests_total counter",
        ]
        for (method, route, bucket), value in sorted(requests.items()):
            lines.append(
                f'nova_http_requests_total{{method="{method}",route="{route}",status="{bucket}"}} {value}'
            )
        lines += [
            "# HELP nova_http_request_duration_ms_total Summed handler duration in milliseconds.",
            "# TYPE nova_http_request_duration_ms_total counter",
        ]
        for (method, route), value in sorted(durations.items()):
            lines.append(f'nova_http_request_duration_ms_total{{method="{method}",route="{route}"}} {value}')
        lines += [
            "# HELP nova_http_requests_in_flight Requests currently being handled.",
            "# TYPE nova_http_requests_in_flight gauge",
            f"nova_http_requests_in_flight {in_flight}",
        ]
        return "\n".join(lines) + "\n"


metrics = RequestMetrics()


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id, log the access line, and record metrics."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = set_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        metrics.start()
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            route = _route_template(request)
            metrics.observe(request.method, route, status_code, duration_ms)
            logger.info(
                "http_request",
                extra={
                    "method": request.method,
                    "route": route,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": round(duration_ms, 2),
                    "request_id": request_id,
                },
            )
            reset_request_id()
