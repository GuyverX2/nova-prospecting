"""Platform JWT bearer authentication. Nova does not implement login."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
from app.tenancy.service import TenantContext

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="disabled")


def create_access_token(claims: dict, expires_in: timedelta = timedelta(minutes=30)) -> str:
    """Test/integration helper; production tokens are issued by the platform."""
    payload = {**claims, "aud": settings.JWT_AUDIENCE, "exp": datetime.now(timezone.utc) + expires_in}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


@dataclass(frozen=True)
class PlatformPrincipal:
    sub: str
    tenant_id: str
    roles: frozenset[str]
    scopes: frozenset[str]
    bearer_token: str


def _principal(token: str) -> PlatformPrincipal:
    try:
        claims = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], audience=settings.JWT_AUDIENCE)
        sub, tenant_id = claims.get("sub"), claims.get("tenant_id")
        roles, scopes = claims.get("roles"), claims.get("scopes")
        if not isinstance(sub, str) or not sub or not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("missing required subject or tenant")
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            raise ValueError("roles claim is required")
        if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
            raise ValueError("scopes claim is required")
        return PlatformPrincipal(sub, tenant_id, frozenset(roles), frozenset(scopes), token)
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid platform bearer token") from exc


def get_platform_principal(token: str = Depends(oauth2_scheme)) -> PlatformPrincipal:
    return _principal(token)


def get_tenant_context(principal: PlatformPrincipal = Depends(get_platform_principal)) -> TenantContext:
    return TenantContext(tenant_id=principal.tenant_id, roles=principal.roles, scopes=principal.scopes)
