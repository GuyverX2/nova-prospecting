"""One bounded, retrying JSON transport for every outbound integration.

Each provider adapter used to hand-roll ``urllib`` with its own timeout, size
limit and error mapping. They now share this module, so a third-party outage
degrades the same way everywhere: bounded time, bounded bytes, bounded retries,
no secret in an exception message, and a typed failure the caller can map.

Retries are only attempted for transport failures and 5xx/429 responses, and
only for requests the caller marks as safe to repeat (idempotent reads, or
writes carrying an idempotency key).
"""
from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.logging import get_logger

logger = get_logger("nova.integration")

DEFAULT_MAX_BYTES = 1_000_000
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class IntegrationError(Exception):
    """Base failure for an outbound provider call."""

    def __init__(self, message: str, *, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class IntegrationUnavailable(IntegrationError):
    """The provider could not be reached, timed out, or answered unusably."""


class IntegrationRejected(IntegrationError):
    """The provider answered with an error status."""


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 1
    backoff_seconds: float = 0.25
    max_backoff_seconds: float = 2.0

    def delay_for(self, attempt: int) -> float:
        return min(self.backoff_seconds * (2 ** (attempt - 1)), self.max_backoff_seconds)


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    json_body: Any | None = None,
    timeout: float = 10.0,
    max_bytes: int = DEFAULT_MAX_BYTES,
    retry: RetryPolicy | None = None,
    provider: str = "provider",
    sleep=time.sleep,
) -> dict[str, Any]:
    """Perform one JSON request and return the decoded object.

    Raises :class:`IntegrationRejected` for an error status and
    :class:`IntegrationUnavailable` for transport, size or decoding failures.
    """
    if not url.startswith(("http://", "https://")):
        # urlopen would happily open file:// or ftp://; provider URLs never are.
        raise IntegrationUnavailable(f"{provider} URL must be http(s)")
    policy = retry or RetryPolicy()
    payload = None if json_body is None else json.dumps(json_body, separators=(",", ":")).encode("utf-8")
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request_headers.setdefault("Accept", "application/json")

    last_error: IntegrationError | None = None
    for attempt in range(1, max(1, policy.attempts) + 1):
        # S310 on the next two lines: the http(s) scheme is validated above,
        # which the rule cannot see.
        request = Request(url, data=payload, method=method.upper(), headers=request_headers)  # noqa: S310
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise IntegrationUnavailable(f"{provider} response exceeded {max_bytes} bytes")
            if not raw:
                return {}
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise IntegrationUnavailable(f"{provider} returned a non-object JSON response")
            return decoded
        except HTTPError as exc:
            # The provider body may echo credentials: never surface or log it.
            last_error = IntegrationRejected(f"{provider} returned HTTP {exc.code}", status_code=exc.code)
            retryable = exc.code in RETRYABLE_STATUS
        except (URLError, TimeoutError, OSError) as exc:
            last_error = IntegrationUnavailable(f"{provider} could not be reached")
            logger.warning(
                "integration_transport_error",
                extra={"provider": provider, "attempt": attempt, "reason": type(exc).__name__},
            )
            retryable = True
        except (UnicodeDecodeError, ValueError) as exc:
            last_error = IntegrationUnavailable(f"{provider} returned an unreadable response")
            logger.warning(
                "integration_decode_error", extra={"provider": provider, "reason": type(exc).__name__}
            )
            retryable = False
        if not retryable or attempt >= policy.attempts:
            break
        sleep(policy.delay_for(attempt))
    raise last_error or IntegrationUnavailable(f"{provider} could not be reached")
