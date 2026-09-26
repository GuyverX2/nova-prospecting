"""Platform JWT bearer authentication. Nova does not implement login."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.tenancy.service import TenantContext

bearer_scheme = HTTPBearer(auto_error=False, description="Platform-issued bearer token")

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid platform bearer token",
    headers={"WWW-Authenticate": "Bearer"},
)


def create_access_token(claims: dict, expires_in: timedelta = timedelta(minutes=30)) -> str:
    """Test/integration helper; production tokens are issued by the platform."""
    payload = {
        **claims,
        "aud": settings.JWT_AUDIENCE,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + expires_in,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


@dataclass(frozen=True)
class PlatformPrincipal:
    sub: str
    tenant_id: str
    roles: frozenset[str]
    scopes: frozenset[str]
    bearer_token: str


def _string_list(claims: dict, name: str) -> frozenset[str]:
    value = claims.get(name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} claim is required")
    return frozenset(value)


def _principal(token: str) -> PlatformPrincipal:
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            audience=settings.JWT_AUDIENCE,
            leeway=settings.JWT_LEEWAY_SECONDS,
            # A platform token without an expiry would never stop working:
            # require it rather than trusting the issuer to have set one.
            options={"require": ["exp", "sub", "aud"], "verify_exp": True, "verify_aud": True},
        )
        sub, tenant_id = claims.get("sub"), claims.get("tenant_id")
        if not isinstance(sub, str) or not sub.strip():
            raise ValueError("missing required subject")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("missing required tenant")
        return PlatformPrincipal(
            sub.strip(),
            tenant_id.strip(),
            _string_list(claims, "roles"),
            _string_list(claims, "scopes"),
            token,
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise _UNAUTHENTICATED from exc


def get_platform_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> PlatformPrincipal:
    if credentials is None or (credentials.scheme or "").lower() != "bearer" or not credentials.credentials:
        raise _UNAUTHENTICATED
    return _principal(credentials.credentials)


def get_tenant_context(principal: PlatformPrincipal = Depends(get_platform_principal)) -> TenantContext:
    return TenantContext(tenant_id=principal.tenant_id, roles=principal.roles, scopes=principal.scopes)
